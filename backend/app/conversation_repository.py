# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import timedelta

from sqlalchemy import Select, and_, func, or_, select, update

from app.db.base import utcnow
from app.errors import ClipoError
from app.models import Note
from app.models.conversation import ConversationJob, NoteConversation
from app.note_repository import NoteRepository
from app.schemas.conversation import (
    ConversationHistory,
    ConversationJobResponse,
    ConversationMessage,
)

ACTIVE = ("queued", "running", "retrying")


class ConversationRepository(NoteRepository):
    def _lock_note(self, note_id: int) -> None:
        result = self.db.execute(
            update(Note)
            .where(Note.id == note_id, Note.user_id == self.user_id)
            .values(updated_at=Note.updated_at)
        )
        if result.rowcount != 1:
            raise ClipoError(404, "note_not_found", "笔记不存在或已删除，请返回笔记列表")

    def messages(self, note_id: int) -> Select[tuple[NoteConversation]]:
        return select(NoteConversation).where(
            NoteConversation.note_id == note_id, NoteConversation.user_id == self.user_id
        )

    def job(self, job_id: str) -> ConversationJob:
        row = self.db.scalar(
            select(ConversationJob).where(
                ConversationJob.id == job_id, ConversationJob.user_id == self.user_id
            )
        )
        if row is None:
            raise ClipoError(404, "conversation_job_not_found", "对话任务不存在，请刷新笔记")
        return row

    def latest(self, note_id: int) -> ConversationJob | None:
        return self.db.scalar(
            select(ConversationJob)
            .where(ConversationJob.note_id == note_id, ConversationJob.user_id == self.user_id)
            .order_by(ConversationJob.turn_index.desc())
            .limit(1)
        )

    def history(self, note_id: int, before: int | None, limit: int) -> ConversationHistory:
        self.note(note_id)
        indices = (
            select(NoteConversation.turn_index)
            .where(NoteConversation.note_id == note_id, NoteConversation.user_id == self.user_id)
            .distinct()
        )
        if before is not None:
            indices = indices.where(NoteConversation.turn_index < before)
        values = list(
            self.db.scalars(indices.order_by(NoteConversation.turn_index.desc()).limit(limit + 1))
        )
        rows = self.db.scalars(
            self.messages(note_id)
            .where(NoteConversation.turn_index.in_(values[:limit]))
            .order_by(NoteConversation.turn_index, NoteConversation.role.desc())
        )
        latest = self.latest(note_id)
        return ConversationHistory(
            turns=[ConversationMessage.model_validate(row) for row in rows],
            next_before=values[limit - 1] if len(values) > limit else None,
            latest_job=ConversationJobResponse.model_validate(latest) if latest else None,
        )

    def question(self, job: ConversationJob) -> str:
        return (
            self.db.scalars(
                self.messages(job.note_id).where(
                    NoteConversation.turn_index == job.turn_index, NoteConversation.role == "user"
                )
            )
            .one()
            .content
        )

    def submit(self, note_id: int, question: str, key: str) -> ConversationJob:
        self._lock_note(note_id)
        existing = self.db.scalar(
            select(ConversationJob).where(
                ConversationJob.user_id == self.user_id, ConversationJob.request_key == key
            )
        )
        if existing:
            if existing.note_id != note_id or self.question(existing) != question:
                raise ClipoError(409, "idempotency_conflict", "此请求已用于其他问题，请刷新后重试")
            return existing
        latest = self.latest(note_id)
        if latest and latest.status in ACTIVE:
            raise ClipoError(409, "conversation_busy", "上一条问题仍在回答中，请稍后再提问")
        turn = self.db.scalar(
            select(func.max(NoteConversation.turn_index)).where(
                NoteConversation.note_id == note_id, NoteConversation.user_id == self.user_id
            )
        )
        index = 0 if turn is None else turn + 1
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        job_id = uuid.uuid4().hex
        self.db.execute(
            insert(ConversationJob)
            .values(
                id=job_id, user_id=self.user_id, note_id=note_id, turn_index=index, request_key=key
            )
            .on_conflict_do_nothing()
        )
        existing = self.db.scalar(
            select(ConversationJob).where(
                ConversationJob.user_id == self.user_id, ConversationJob.request_key == key
            )
        )
        if existing is None or existing.id != job_id:
            raise ClipoError(409, "idempotency_conflict", "此请求已用于其他问题，请刷新后重试")
        self.db.add(
            NoteConversation(
                id=uuid.uuid4().hex,
                user_id=self.user_id,
                note_id=note_id,
                turn_index=index,
                role="user",
                content=question,
            )
        )
        self.db.flush()
        return existing

    def retry(self, job_id: str) -> ConversationJob:
        job = self.job(job_id)
        self._lock_note(job.note_id)
        self.db.refresh(job)
        latest = self.latest(job.note_id)
        if latest is None or latest.id != job.id or job.status != "failed":
            raise ClipoError(409, "conversation_not_failed", "仅可重试最新的失败问题，请刷新对话")
        job.status, job.attempts, job.last_error = "queued", 0, None
        job.execution_id = job.lease_expires_at = job.next_retry_at = None
        job.updated_at = utcnow()
        self.db.flush()
        return job

    def completed(
        self, note_id: int, before: int | None = None, limit: int | None = None
    ) -> list[NoteConversation]:
        # The assistant row is the durable completion marker, including restored conversations.
        indices = select(NoteConversation.turn_index).where(
            NoteConversation.user_id == self.user_id,
            NoteConversation.note_id == note_id,
            NoteConversation.role == "assistant",
        )
        if before is not None:
            indices = indices.where(NoteConversation.turn_index < before)
        indices = indices.order_by(NoteConversation.turn_index.desc())
        if limit is not None:
            indices = indices.limit(limit)
        return list(
            self.db.scalars(
                self.messages(note_id)
                .where(NoteConversation.turn_index.in_(indices))
                .order_by(NoteConversation.turn_index, NoteConversation.role.desc())
            )
        )

    def claim(self, job_id: str, execution: str) -> ConversationJob | None:
        now = utcnow()
        result = self.db.execute(
            update(ConversationJob)
            .where(
                ConversationJob.id == job_id,
                ConversationJob.user_id == self.user_id,
                ConversationJob.attempts < 4,
                or_(
                    ConversationJob.status == "queued",
                    and_(
                        ConversationJob.status == "retrying", ConversationJob.next_retry_at <= now
                    ),
                    and_(
                        ConversationJob.status == "running", ConversationJob.lease_expires_at <= now
                    ),
                ),
            )
            .values(
                status="running",
                attempts=ConversationJob.attempts + 1,
                execution_id=execution,
                lease_expires_at=now + timedelta(minutes=10),
                next_retry_at=None,
                updated_at=now,
            )
        )
        return self.job(job_id) if result.rowcount == 1 else None

    def finish(self, job_id: str, execution: str, answer: str) -> None:
        result = self.db.execute(
            update(ConversationJob)
            .where(
                ConversationJob.id == job_id,
                ConversationJob.user_id == self.user_id,
                ConversationJob.status == "running",
                ConversationJob.execution_id == execution,
            )
            .values(
                status="success",
                last_error=None,
                execution_id=None,
                lease_expires_at=None,
                next_retry_at=None,
                updated_at=utcnow(),
            )
        )
        if result.rowcount != 1:
            return
        job = self.job(job_id)
        self.db.add(
            NoteConversation(
                id=uuid.uuid4().hex,
                user_id=self.user_id,
                note_id=job.note_id,
                turn_index=job.turn_index,
                role="assistant",
                content=answer,
            )
        )

    def fail(self, job_id: str, execution: str, message: str, delay: int | None) -> None:
        self.db.execute(
            update(ConversationJob)
            .where(
                ConversationJob.id == job_id,
                ConversationJob.user_id == self.user_id,
                ConversationJob.status == "running",
                ConversationJob.execution_id == execution,
            )
            .values(
                status="failed" if delay is None else "retrying",
                last_error=message,
                next_retry_at=utcnow() + timedelta(seconds=delay) if delay is not None else None,
                execution_id=None,
                lease_expires_at=None,
                updated_at=utcnow(),
            )
        )
