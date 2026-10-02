# SPDX-License-Identifier: AGPL-3.0-or-later
import logging
import uuid

from huey import SqliteHuey
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.conversation_repository import ConversationRepository
from app.db.base import utcnow
from app.llm.client import CompatibleClient
from app.llm.orchestrator import load_config
from app.model_usage_repository import ModelQuotaExceeded
from app.models.conversation import ConversationJob
from app.services.conversations import answer_question, build_messages
from app.services.model_usage import MeteredClient

logger = logging.getLogger("clipo.conversations")
RETRY_DELAYS = (30, 120, 480)


class ConversationQueue:
    def __init__(
        self, huey: SqliteHuey, sessions: sessionmaker[Session], settings: Settings
    ) -> None:
        self.sessions, self.settings = sessions, settings
        self.llm = CompatibleClient()

        @huey.task(name="clipo.conversation")
        def task(user_id: int, job_id: str) -> None:
            delay = self.run(user_id, job_id)
            if delay is not None:
                task.schedule(args=(user_id, job_id), delay=delay)

        self.task = task

    def enqueue(self, user_id: int, job_id: str) -> None:
        try:
            self.task(user_id, job_id)
        except Exception:
            logger.error("Conversation dispatch failed; job %s will be recovered", job_id)

    def run(self, user_id: int, job_id: str) -> int | None:
        execution = uuid.uuid4().hex
        with self.sessions.begin() as db:
            job = ConversationRepository(db, user_id).claim(job_id, execution)
            if job is None:
                return None
            note_id, turn, attempts = job.note_id, job.turn_index, job.attempts
        delay = RETRY_DELAYS[attempts - 1] if attempts <= len(RETRY_DELAYS) else None
        try:
            with self.sessions.begin() as db:
                repository = ConversationRepository(db, user_id)
                config = load_config(repository, self.settings)
                if not config.api_key:
                    repository.fail(
                        job_id, execution, "尚未配置模型密钥，请在设置中配置后重试", None
                    )
                    return None
                messages = build_messages(
                    repository.note(note_id),
                    repository.completed(note_id, before=turn, limit=10),
                    repository.question(repository.job(job_id)),
                    config.token_budget,
                )
            answer = answer_question(
                messages, config, MeteredClient(self.llm, self.sessions, user_id)
            )
            with self.sessions.begin() as db:
                ConversationRepository(db, user_id).finish(job_id, execution, answer)
            return None
        except ModelQuotaExceeded as exc:
            with self.sessions.begin() as db:
                ConversationRepository(db, user_id).fail(job_id, execution, exc.message, None)
            return None
        except Exception:
            with self.sessions.begin() as db:
                ConversationRepository(db, user_id).fail(
                    job_id,
                    execution,
                    "回答生成失败，问题和历史已保留；请检查模型设置或稍后重试",
                    delay,
                )
            logger.warning("Conversation job %s failed, attempt %s", job_id, attempts)
            return delay

    def recover(self) -> None:
        now = utcnow()
        with self.sessions.begin() as db:
            db.execute(
                update(ConversationJob)
                .where(
                    ConversationJob.status == "running",
                    ConversationJob.lease_expires_at <= now,
                    ConversationJob.attempts >= 4,
                )
                .values(
                    status="failed",
                    last_error="回答生成被中断，问题和历史已保留；请重试",
                    execution_id=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
            )
            pending = list(
                db.execute(
                    select(ConversationJob.user_id, ConversationJob.id)
                    .where(
                        or_(
                            ConversationJob.status == "queued",
                            and_(
                                ConversationJob.status == "retrying",
                                ConversationJob.next_retry_at <= now,
                            ),
                            and_(
                                ConversationJob.status == "running",
                                ConversationJob.lease_expires_at <= now,
                            ),
                        ),
                    )
                    .order_by(ConversationJob.updated_at)
                    .limit(100)
                )
            )
        for user_id, job_id in pending:
            self.enqueue(user_id, job_id)
