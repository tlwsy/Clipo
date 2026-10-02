# SPDX-License-Identifier: AGPL-3.0-or-later
import logging
import uuid

from huey import SqliteHuey
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.base import utcnow
from app.embedding_repository import EmbeddingRepository
from app.model_usage_repository import ModelQuotaExceeded
from app.models import EmbeddingJob
from app.services.embeddings import (
    EMBEDDING_ERROR,
    EmbeddingClient,
    digest,
    load_embedding_config,
    note_input,
    validate_vector,
)
from app.services.model_usage import reserve_model_call

logger = logging.getLogger("clipo.embeddings")
RETRY_DELAYS = (30, 120, 480)


class EmbeddingQueue:
    def __init__(
        self, huey: SqliteHuey, sessions: sessionmaker[Session], settings: Settings
    ) -> None:
        self.sessions, self.settings = sessions, settings
        self.client = EmbeddingClient()

        @huey.task(name="clipo.embedding")
        def task(user_id: int, job_id: str) -> None:
            delay = self.run(user_id, job_id)
            if delay is not None:
                task.schedule(args=(user_id, job_id), delay=delay)
            with self.sessions() as db:
                job = EmbeddingRepository(db, user_id).job(job_id)
                backfill = job is not None and job.kind == "backfill"
            if backfill:
                self.dispatch_pending(user_id)

        self.task = task

    def enqueue(self, user_id: int, job_id: str) -> None:
        try:
            self.task(user_id, job_id)
        except Exception:
            logger.warning("Embedding dispatch failed; job %s will be recovered", job_id)

    def run(self, user_id: int, job_id: str) -> int | None:
        execution_id = uuid.uuid4().hex
        with self.sessions.begin() as db:
            job = EmbeddingRepository(db, user_id).claim(job_id, execution_id)
            if job is None:
                return None
            attempts, kind = job.attempts, job.kind
        delays = (2, 5) if kind == "query" else RETRY_DELAYS
        delay = delays[attempts - 1] if attempts <= len(delays) else None
        try:
            with self.sessions.begin() as db:
                repository = EmbeddingRepository(db, user_id)
                job = repository.fence(job_id, execution_id)
                if job is None:
                    return None
                config = load_embedding_config(repository, self.settings)
                if not config.enabled or not config.api_key:
                    repository.fail(
                        job_id, execution_id, "请在模型设置中开启语义搜索并配置密钥", None
                    )
                    return None
                if job.kind == "backfill":
                    return 0 if repository.backfill_batch(job_id, execution_id, config) else None
                if job.kind == "query" and job.config_key != config.key:
                    repository.fail(job_id, execution_id, "模型配置已改变，请重新搜索", None)
                    return None
                value = note_input(repository.note(job.note_id)) if job.note_id else job.input_text
                if not value:
                    raise ValueError("Missing embedding input")
                content_hash = digest(value)
            reserve_model_call(self.sessions, user_id)
            vector = validate_vector(self.client.embed(config, value))
            with self.sessions.begin() as db:
                repository = EmbeddingRepository(db, user_id)
                current = load_embedding_config(repository, self.settings)
                if not current.enabled or current.key != config.key:
                    job = repository.fence(job_id, execution_id)
                    if job is not None and job.note_id is not None:
                        repository.invalidate_note(repository.note(job.note_id))
                    elif job is not None:
                        repository.fail(job_id, execution_id, "模型配置已改变，请重新搜索", None)
                    return None
                repository.finish(job_id, execution_id, config, content_hash, vector)
        except ModelQuotaExceeded as exc:
            with self.sessions.begin() as db:
                EmbeddingRepository(db, user_id).fail(job_id, execution_id, exc.message, None)
            return None
        except Exception:
            with self.sessions.begin() as db:
                EmbeddingRepository(db, user_id).fail(job_id, execution_id, EMBEDDING_ERROR, delay)
            # Never log exception strings, model addresses, queries or provider bodies.
            logger.warning("Embedding job %s failed, attempt %s", job_id, attempts)
            return delay
        return None

    def dispatch_pending(self, user_id: int | None = None) -> None:
        now = utcnow()
        with self.sessions() as db:
            query = select(EmbeddingJob.user_id, EmbeddingJob.id).where(
                or_(EmbeddingJob.expires_at.is_(None), EmbeddingJob.expires_at > now),
                or_(
                    EmbeddingJob.status == "queued",
                    and_(EmbeddingJob.status == "retrying", EmbeddingJob.next_retry_at <= now),
                    and_(EmbeddingJob.status == "running", EmbeddingJob.lease_expires_at <= now),
                ),
            )
            if user_id is not None:
                query = query.where(EmbeddingJob.user_id == user_id)
            rows = list(db.execute(query.order_by(EmbeddingJob.updated_at).limit(100)))
        for owner, identifier in rows:
            self.enqueue(owner, identifier)

    def recover(self) -> None:
        now = utcnow()
        with self.sessions.begin() as db:
            # Global maintenance only discovers owners; mutations use scoped repositories.
            stale = list(
                db.execute(
                    select(EmbeddingJob.user_id, EmbeddingJob.id, EmbeddingJob.execution_id)
                    .where(
                        EmbeddingJob.status == "running",
                        EmbeddingJob.lease_expires_at <= now,
                        EmbeddingJob.attempts >= 4,
                    )
                    .limit(100)
                )
            )
            for owner, identifier, execution in stale:
                EmbeddingRepository(db, owner).fail(identifier, execution, EMBEDDING_ERROR, None)
            owners = list(
                db.scalars(
                    select(EmbeddingJob.user_id)
                    .where(EmbeddingJob.kind == "query", EmbeddingJob.expires_at <= now)
                    .distinct()
                    .limit(100)
                )
            )
            for owner in owners:
                EmbeddingRepository(db, owner).cleanup_queries()
            # Finished outbox entries for deleted notes cascade with the note.
        self.dispatch_pending()
