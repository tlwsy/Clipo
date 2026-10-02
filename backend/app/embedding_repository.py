# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import timedelta

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import utcnow
from app.models import EmbeddingJob, Note
from app.note_repository import NoteRepository
from app.services.embeddings import EmbeddingConfig, digest, note_input

ACTIVE = ("queued", "running", "retrying")


class EmbeddingRepository(NoteRepository):
    def job(self, job_id: str) -> EmbeddingJob | None:
        return self.db.scalar(
            select(EmbeddingJob).where(
                EmbeddingJob.id == job_id, EmbeddingJob.user_id == self.user_id
            )
        )

    def target(self, key: str) -> EmbeddingJob | None:
        return self.db.scalar(
            select(EmbeddingJob).where(
                EmbeddingJob.target_key == key, EmbeddingJob.user_id == self.user_id
            )
        )

    def _request(
        self,
        target: str,
        kind: str,
        *,
        replace: bool = False,
        replace_when: ColumnElement[bool] | None = None,
        **values: object,
    ) -> EmbeddingJob:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        data = dict(
            id=uuid.uuid4().hex,
            user_id=self.user_id,
            target_key=target,
            kind=kind,
            status="queued",
            attempts=0,
            config_key="",
            content_hash="",
            cursor=0,
            through_id=0,
            updated_at=utcnow(),
            execution_id=None,
            lease_expires_at=None,
            next_retry_at=None,
            last_error=None,
            vector=None,
        )
        data.update(values)
        statement = insert(EmbeddingJob).values(**data)
        statement = (
            statement.on_conflict_do_update(
                index_elements=["user_id", "target_key"], set_=data, where=replace_when
            )
            if replace
            else statement.on_conflict_do_nothing(index_elements=["user_id", "target_key"])
        )
        self.db.execute(statement)
        self.db.expire_all()
        row = self.target(target)
        assert row is not None
        return row

    def invalidate_note(self, note: Note) -> None:
        if note.user_id != self.user_id:
            raise ValueError("Invalid note owner")
        note.embedding = None
        note.embedding_key = note.embedding_hash = note.embedding_error = None
        self.db.flush()
        # Disabled accounts never incur model calls. Backfill covers their existing notes later.
        if self.settings().llm_config.get("embedding_enabled", False):
            self._request(f"note:{note.id}", "note", note_id=note.id, replace=True)
        else:
            self.db.execute(
                delete(EmbeddingJob).where(
                    EmbeddingJob.user_id == self.user_id,
                    EmbeddingJob.target_key == f"note:{note.id}",
                )
            )

    def request_note(self, note: Note, config: EmbeddingConfig) -> EmbeddingJob | None:
        if note.user_id != self.user_id:
            raise ValueError("Invalid note owner")
        content_hash = digest(note_input(note))
        if note.embedding_key == config.key and note.embedding_hash == content_hash:
            return None
        key = f"note:{note.id}"
        current = self.target(key)
        if current is not None and current.status in ACTIVE:
            return current
        return self._request(
            key,
            "note",
            note_id=note.id,
            replace=True,
            replace_when=EmbeddingJob.status.not_in(ACTIVE),
        )

    def request_backfill(self, *, restart: bool = False) -> EmbeddingJob:
        self.db.execute(
            delete(EmbeddingJob).where(
                EmbeddingJob.user_id == self.user_id,
                EmbeddingJob.kind == "query",
                EmbeddingJob.status == "failed",
            )
        )
        current = self.target("backfill")
        if not restart and current is not None and current.status in ACTIVE:
            return current
        last_id = self.db.scalar(select(func.max(Note.id)).where(Note.user_id == self.user_id)) or 0
        return self._request(
            "backfill",
            "backfill",
            replace=True,
            through_id=last_id,
            replace_when=None if restart else EmbeddingJob.status.not_in(ACTIVE),
        )

    def request_query(self, query: str, config: EmbeddingConfig) -> EmbeddingJob:
        key = "query:" + digest(config.key + "\n" + query)
        current = self.target(key)
        if current is not None and current.expires_at and current.expires_at > utcnow():
            return current
        return self._request(
            key,
            "query",
            replace=True,
            replace_when=EmbeddingJob.expires_at <= utcnow(),
            input_text=query,
            config_key=config.key,
            expires_at=utcnow() + timedelta(minutes=10),
        )

    def claim(self, job_id: str, execution_id: str) -> EmbeddingJob | None:
        now = utcnow()
        result = self.db.execute(
            update(EmbeddingJob)
            .where(
                EmbeddingJob.id == job_id,
                EmbeddingJob.user_id == self.user_id,
                EmbeddingJob.attempts < 4,
                or_(EmbeddingJob.expires_at.is_(None), EmbeddingJob.expires_at > now),
                or_(
                    EmbeddingJob.status == "queued",
                    and_(EmbeddingJob.status == "retrying", EmbeddingJob.next_retry_at <= now),
                    and_(EmbeddingJob.status == "running", EmbeddingJob.lease_expires_at <= now),
                ),
            )
            .values(
                status="running",
                execution_id=execution_id,
                attempts=EmbeddingJob.attempts + 1,
                updated_at=now,
                lease_expires_at=now + timedelta(seconds=90),
            )
        )
        return self.job(job_id) if result.rowcount == 1 else None

    def fence(self, job_id: str, execution_id: str) -> EmbeddingJob | None:
        changed = self.db.execute(
            update(EmbeddingJob)
            .where(
                EmbeddingJob.id == job_id,
                EmbeddingJob.user_id == self.user_id,
                EmbeddingJob.status == "running",
                EmbeddingJob.execution_id == execution_id,
            )
            .values(updated_at=utcnow())
        )
        return self.job(job_id) if changed.rowcount == 1 else None

    def finish(
        self,
        job_id: str,
        execution_id: str,
        config: EmbeddingConfig,
        content_hash: str,
        vector: list[float],
    ) -> None:
        job = self.fence(job_id, execution_id)
        if job is None:
            return
        if job.note_id is not None:
            note = self.note(job.note_id)
            if digest(note_input(note)) != content_hash:
                self.invalidate_note(note)
                return
            note.embedding, note.embedding_key = vector, config.key
            note.embedding_hash, note.embedding_error = content_hash, None
        else:
            job.vector = vector
        job.config_key, job.content_hash = config.key, content_hash
        job.status = "ready"
        job.execution_id = job.lease_expires_at = job.next_retry_at = job.last_error = None

    def fail(self, job_id: str, execution_id: str, message: str, delay: int | None) -> None:
        job = self.fence(job_id, execution_id)
        if job is None:
            return
        job.status = "retrying" if delay is not None else "failed"
        job.last_error, job.execution_id, job.lease_expires_at = message, None, None
        job.next_retry_at = utcnow() + timedelta(seconds=delay) if delay is not None else None
        if job.note_id is not None:
            self.note(job.note_id).embedding_error = message

    def backfill_batch(self, job_id: str, execution_id: str, config: EmbeddingConfig) -> bool:
        job = self.fence(job_id, execution_id)
        if job is None:
            return False
        rows = list(
            self.db.scalars(
                select(Note)
                .where(
                    Note.user_id == self.user_id,
                    Note.id > job.cursor,
                    Note.id <= job.through_id,
                )
                .order_by(Note.id)
                .limit(50)
            )
        )
        for note in rows:
            self.request_note(note, config)
        job = self.job(job_id)
        assert job is not None
        job.cursor = rows[-1].id if rows else job.through_id
        more = len(rows) == 50 and job.cursor < job.through_id
        job.status, job.attempts = ("queued" if more else "ready"), 0
        job.execution_id = job.lease_expires_at = None
        return more

    def index_status(self, config: EmbeddingConfig) -> dict:
        total, ready, failed = self.db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((Note.embedding_key == config.key, 1), else_=0)), 0),
                func.coalesce(func.sum(case((Note.embedding_error.is_not(None), 1), else_=0)), 0),
            )
            .select_from(Note)
            .where(Note.user_id == self.user_id)
        ).one()
        pending = (
            self.db.scalar(
                select(func.count())
                .select_from(EmbeddingJob)
                .where(
                    EmbeddingJob.user_id == self.user_id,
                    EmbeddingJob.kind == "note",
                    EmbeddingJob.status.in_(ACTIVE),
                )
            )
            or 0
        )
        backfill = self.target("backfill")
        return dict(
            total=total,
            ready=ready,
            failed=failed,
            pending=pending,
            backfill_running=bool(backfill and backfill.status in ACTIVE),
        )

    def cleanup_queries(self) -> None:
        self.db.execute(
            delete(EmbeddingJob).where(
                EmbeddingJob.user_id == self.user_id,
                EmbeddingJob.kind == "query",
                EmbeddingJob.expires_at <= utcnow(),
            )
        )
