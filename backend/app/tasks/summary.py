# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import logging
import uuid

from huey import SqliteHuey
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.base import utcnow
from app.extractors.base import CapturedComment, CapturedContent
from app.llm.client import CompatibleClient
from app.llm.orchestrator import load_config, summarize
from app.models import SummaryJob
from app.summary_repository import SummaryRepository

logger = logging.getLogger("clipo.summary")
RETRY_DELAYS = (30, 120, 480)


class SummaryQueue:
    def __init__(
        self, huey: SqliteHuey, sessions: sessionmaker[Session], settings: Settings
    ) -> None:
        self.sessions, self.settings = sessions, settings
        self.llm = CompatibleClient()

        @huey.task(name="clipo.summary")
        def task(user_id: int, job_id: str) -> None:
            delay = self.run(user_id, job_id)
            if delay is not None:
                task.schedule(args=(user_id, job_id), delay=delay)

        self.task = task

    def enqueue(self, user_id: int, job_id: str) -> None:
        try:
            self.task(user_id, job_id)
        except Exception:
            logger.error("Summary dispatch failed; job %s will be recovered", job_id)

    def run(self, user_id: int, job_id: str) -> int | None:
        execution_id = uuid.uuid4().hex
        with self.sessions.begin() as db:
            job = SummaryRepository(db, user_id).claim_summary(job_id, execution_id)
            if job is None:
                return None
            note_id, attempts = job.note_id, job.attempts
        delay = RETRY_DELAYS[attempts - 1] if attempts <= len(RETRY_DELAYS) else None
        try:
            with self.sessions() as db:
                repository = SummaryRepository(db, user_id)
                note = repository.note(note_id)
                content = CapturedContent.model_validate(note.content).model_copy(
                    update={
                        "comments": [
                            CapturedComment(
                                author=row.author,
                                content=row.content,
                                likes=row.likes,
                                replies=row.replies,
                            )
                            for row in repository.comments(note_id)
                        ]
                    }
                )
                config = load_config(repository, self.settings)
            result = summarize(content, config, self.llm)
            with self.sessions.begin() as db:
                repository = SummaryRepository(db, user_id)
                if result.summary is not None:
                    repository.finish_summary(job_id, execution_id, result)
                    return None
                if not config.api_key:
                    delay = None
                repository.fail_summary(
                    job_id,
                    execution_id,
                    "重新生成摘要失败，已有内容已保留。" + (result.error or "请检查模型设置后重试"),
                    delay,
                )
        except Exception:
            with self.sessions.begin() as db:
                SummaryRepository(db, user_id).fail_summary(
                    job_id,
                    execution_id,
                    "重新生成摘要失败，已有内容已保留；请检查模型设置或稍后重试",
                    delay,
                )
            logger.warning("Summary job %s failed, attempt %s", job_id, attempts)
        return delay

    def recover(self) -> None:
        now = utcnow()
        with self.sessions.begin() as db:
            db.execute(
                update(SummaryJob)
                .where(
                    SummaryJob.status == "running",
                    SummaryJob.lease_expires_at <= now,
                    SummaryJob.attempts >= 4,
                )
                .values(
                    status="failed",
                    last_error="摘要任务被中断，已有内容已保留；请重试",
                    execution_id=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
            )
            pending = list(
                db.execute(
                    select(SummaryJob.user_id, SummaryJob.id)
                    .where(
                        or_(
                            SummaryJob.status == "queued",
                            and_(SummaryJob.status == "retrying", SummaryJob.next_retry_at <= now),
                            and_(
                                SummaryJob.status == "running", SummaryJob.lease_expires_at <= now
                            ),
                        )
                    )
                    .order_by(SummaryJob.updated_at)
                    .limit(100)
                )
            )
        for user_id, job_id in pending:
            self.enqueue(user_id, job_id)
