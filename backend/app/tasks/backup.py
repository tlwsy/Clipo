# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import logging
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

from huey import SqliteHuey
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.backup_repository import BackupRepository, due_jobs
from app.config import Settings
from app.db.base import utcnow
from app.errors import ClipoError
from app.models import BackupJob, UserSettings
from app.schemas.backup import Archive
from app.services.backup import job_directory, write_archive
from app.services.backup_settings import schedule_match
from app.storage.backup import store_backup

logger = logging.getLogger("clipo.backup")


class BackupQueue:
    def __init__(
        self, huey: SqliteHuey, sessions: sessionmaker[Session], settings: Settings
    ) -> None:
        self.sessions, self.settings = sessions, settings

        @huey.task(name="clipo.backup")
        def execute(user_id: int, job_id: str) -> None:
            self.run(user_id, job_id)

        self.execute = execute

    def enqueue(self, user_id: int, job_id: str) -> None:
        try:
            self.execute(user_id, job_id)
        except Exception:
            logger.warning("Backup dispatch deferred for %s", job_id)

    def run(self, user_id: int, job_id: str) -> None:
        execution = uuid.uuid4().hex
        with self.sessions.begin() as db:
            job = BackupRepository(db, user_id).claim_backup(job_id, execution)
            if job is None:
                return
            kind, attempts = job.kind, job.attempts
        directory = job_directory(self.settings, user_id, job_id)
        artifact = None
        try:
            if kind == "import":
                archive = Archive.model_validate_json((directory / "input.json").read_bytes())
                with self.sessions.begin() as db:
                    repository = BackupRepository(db, user_id)
                    if not repository.fence_backup(job_id, execution):
                        return
                    count = repository.restore(archive)
                    repository.fence_backup(
                        job_id,
                        execution,
                        status="success",
                        note_count=count,
                        last_error=None,
                        lease_expires_at=None,
                    )
                (directory / "input.json").unlink(missing_ok=True)
            else:
                with self.sessions() as db:
                    # Explicit snapshots include tags, notes, sources and comments together.
                    if db.get_bind().dialect.name == "sqlite":
                        db.connection().exec_driver_sql("BEGIN")
                    else:
                        db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                    artifact, count = write_archive(
                        BackupRepository(db, user_id), directory, execution
                    )
                if kind == "backup":
                    with self.sessions() as db:
                        config = BackupRepository(db, user_id).settings().backup_config
                    if config.get("target", "none") == "none":
                        raise ClipoError(422, "backup_disabled", "请先配置备份目标再重试")
                    store_backup(directory / artifact, user_id, job_id, config, self.settings)
                with self.sessions.begin() as db:
                    accepted = BackupRepository(db, user_id).fence_backup(
                        job_id,
                        execution,
                        status="success",
                        artifact=artifact,
                        note_count=count,
                        last_error=None,
                        lease_expires_at=None,
                    )
                if not accepted:
                    (directory / artifact).unlink(missing_ok=True)
        except Exception as exc:
            permanent = isinstance(exc, (ValidationError, ClipoError))
            message = (
                "备份文件格式或版本无效，请使用 Clipo 导出的 library.json"
                if isinstance(exc, ValidationError)
                else (
                    exc.message
                    if isinstance(exc, ClipoError)
                    else "备份处理失败，请检查存储空间、文件权限和目标配置后重试"
                )
            )
            with self.sessions.begin() as db:
                BackupRepository(db, user_id).fence_backup(
                    job_id,
                    execution,
                    status="failed" if permanent or attempts >= 4 else "retrying",
                    last_error=message,
                    lease_expires_at=None,
                    next_retry_at=utcnow() + timedelta(seconds=30 * attempts),
                )
            if artifact:
                (directory / artifact).unlink(missing_ok=True)
            logger.warning("Backup %s failed (%s)", job_id, type(exc).__name__)

    def recover(self) -> None:
        self.schedule()
        with self.sessions.begin() as db:
            # Global scans dispatch identifiers only; all content uses scoped repositories.
            db.execute(
                update(BackupJob)
                .where(due_jobs(), BackupJob.attempts >= 4)
                .values(
                    status="failed",
                    last_error="任务多次中断，请手动重试",
                    execution_id=None,
                    lease_expires_at=None,
                    updated_at=utcnow(),
                )
            )
            pending = list(
                db.execute(
                    select(BackupJob.user_id, BackupJob.id)
                    .where(due_jobs(), BackupJob.attempts < 4)
                    .order_by(BackupJob.created_at)
                    .limit(100)
                )
            )
        for user_id, job_id in pending:
            self.enqueue(user_id, job_id)
        self.cleanup()

    def schedule(self) -> None:
        now = utcnow()
        try:
            local_time = now.astimezone(ZoneInfo(self.settings.timezone))
        except Exception:
            logger.warning("Backup scheduler timezone is invalid")
            return
        with self.sessions() as db:
            users = list(db.scalars(select(UserSettings.user_id)))
        for user_id in users:
            with self.sessions.begin() as db:
                repository = BackupRepository(db, user_id)
                config = repository.settings().backup_config
                if config.get("target", "none") == "none" or not config.get("schedule"):
                    continue
                if schedule_match(config["schedule"])(local_time):
                    repository.create_backup_job(
                        "backup", "scheduled:" + now.strftime("%Y%m%d%H%M")
                    )

    def cleanup(self) -> None:
        cutoff = utcnow() - timedelta(days=self.settings.export_retention_days)
        with self.sessions() as db:
            expired = list(
                db.execute(
                    select(BackupJob.user_id, BackupJob.id)
                    .where(
                        BackupJob.status == "success",
                        BackupJob.updated_at < cutoff,
                        BackupJob.artifact.is_not(None),
                        BackupJob.artifact != "expired.zip",
                    )
                    .limit(100)
                )
            )
        for user_id, job_id in expired:
            with self.sessions.begin() as db:
                repository = BackupRepository(db, user_id)
                job = repository.backup_job(job_id)
                directory = job_directory(self.settings, user_id, job_id)
                for path in directory.glob("*.zip"):
                    path.unlink(missing_ok=True)
                job.artifact = "expired.zip"
