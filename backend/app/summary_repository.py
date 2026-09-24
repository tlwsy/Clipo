# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import timedelta

from sqlalchemy import and_, or_, select, update

from app.db.base import utcnow
from app.errors import ClipoError
from app.llm.orchestrator import SummaryResult
from app.models import Note, SummaryJob, SummaryRequestKey
from app.note_repository import NoteRepository

ACTIVE = ("queued", "running", "retrying")


class SummaryRepository(NoteRepository):
    def summary_job(self, job_id: str) -> SummaryJob:
        job = self.db.scalar(
            select(SummaryJob).where(SummaryJob.id == job_id, SummaryJob.user_id == self.user_id)
        )
        if job is None:
            raise ClipoError(404, "summary_job_not_found", "摘要任务不存在，请刷新笔记")
        return job

    def latest_summary(self, note_id: int) -> SummaryJob | None:
        self.note(note_id)
        return self.db.scalar(
            select(SummaryJob)
            .where(SummaryJob.user_id == self.user_id, SummaryJob.note_id == note_id)
            .order_by(SummaryJob.created_at.desc(), SummaryJob.id.desc())
            .limit(1)
        )

    def _lock_note(self, note_id: int) -> None:
        # Serialize submission/retry with deletion on both supported databases.
        result = self.db.execute(
            update(Note)
            .where(Note.id == note_id, Note.user_id == self.user_id)
            .values(updated_at=Note.updated_at)
        )
        if result.rowcount != 1:
            raise ClipoError(404, "note_not_found", "笔记不存在或已删除，请返回笔记列表")

    def submit_summary(self, note_id: int, key: str) -> SummaryJob:
        self._lock_note(note_id)
        existing = self.db.scalar(
            select(SummaryJob)
            .join(SummaryRequestKey)
            .where(
                SummaryJob.user_id == self.user_id,
                SummaryRequestKey.user_id == self.user_id,
                SummaryRequestKey.request_key == key,
            )
        )
        if existing:
            if existing.note_id != note_id:
                raise ClipoError(409, "idempotency_conflict", "此请求已用于其他笔记，请刷新后重试")
            return existing
        active = self.db.scalar(
            select(SummaryJob).where(
                SummaryJob.user_id == self.user_id,
                SummaryJob.note_id == note_id,
                SummaryJob.status.in_(ACTIVE),
            )
        )
        if active:
            self._remember_request(active.id, note_id, key)
            return active
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        job_id = uuid.uuid4().hex
        self.db.execute(
            insert(SummaryJob)
            .values(id=job_id, user_id=self.user_id, note_id=note_id, request_key=key)
            .on_conflict_do_nothing()
        )
        # The key may also have been submitted concurrently for another note.
        existing = self.db.scalar(
            select(SummaryJob).where(
                SummaryJob.user_id == self.user_id, SummaryJob.request_key == key
            )
        )
        if existing is None or existing.note_id != note_id:
            raise ClipoError(409, "idempotency_conflict", "此请求已用于其他笔记，请刷新后重试")
        self._remember_request(existing.id, note_id, key)
        return existing

    def _remember_request(self, job_id: str, note_id: int, key: str) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        self.db.execute(
            insert(SummaryRequestKey)
            .values(
                user_id=self.user_id,
                request_key=key,
                job_id=job_id,
            )
            .on_conflict_do_nothing()
        )
        remembered = self.db.scalar(
            select(SummaryJob)
            .join(SummaryRequestKey)
            .where(
                SummaryJob.user_id == self.user_id,
                SummaryRequestKey.user_id == self.user_id,
                SummaryRequestKey.request_key == key,
            )
        )
        if remembered is None or remembered.note_id != note_id or remembered.id != job_id:
            raise ClipoError(409, "idempotency_conflict", "此请求已用于其他笔记，请刷新后重试")

    def retry_summary(self, job_id: str) -> SummaryJob:
        job = self.summary_job(job_id)
        self._lock_note(job.note_id)
        self.db.refresh(job)
        latest = self.latest_summary(job.note_id)
        if latest is None or latest.id != job.id or job.status != "failed":
            raise ClipoError(409, "summary_not_failed", "仅可重试最新的失败摘要任务，请刷新笔记")
        job.status, job.attempts, job.last_error = "queued", 0, None
        job.execution_id = job.lease_expires_at = job.next_retry_at = None
        job.updated_at = utcnow()
        self.db.flush()
        return job

    def claim_summary(self, job_id: str, execution_id: str) -> SummaryJob | None:
        now = utcnow()
        result = self.db.execute(
            update(SummaryJob)
            .where(
                SummaryJob.id == job_id,
                SummaryJob.user_id == self.user_id,
                SummaryJob.attempts < 4,
                or_(
                    SummaryJob.status == "queued",
                    and_(SummaryJob.status == "retrying", SummaryJob.next_retry_at <= now),
                    and_(SummaryJob.status == "running", SummaryJob.lease_expires_at <= now),
                ),
            )
            .values(
                status="running",
                attempts=SummaryJob.attempts + 1,
                execution_id=execution_id,
                lease_expires_at=now + timedelta(minutes=10),
                next_retry_at=None,
                updated_at=now,
            )
        )
        return self.summary_job(job_id) if result.rowcount == 1 else None

    def fail_summary(self, job_id: str, execution_id: str, message: str, delay: int | None) -> None:
        self.db.execute(
            update(SummaryJob)
            .where(
                SummaryJob.id == job_id,
                SummaryJob.user_id == self.user_id,
                SummaryJob.status == "running",
                SummaryJob.execution_id == execution_id,
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

    def finish_summary(self, job_id: str, execution_id: str, result: SummaryResult) -> None:
        fenced = self.db.execute(
            update(SummaryJob)
            .where(
                SummaryJob.id == job_id,
                SummaryJob.user_id == self.user_id,
                SummaryJob.status == "running",
                SummaryJob.execution_id == execution_id,
            )
            .values(updated_at=utcnow())
        )
        if fenced.rowcount != 1:
            return
        job = self.summary_job(job_id)
        note = self.note(job.note_id)
        summary = result.summary
        if summary is None:
            raise ValueError("Cannot apply an unsuccessful summary")
        note.summary_markdown = summary.summary_markdown
        note.key_points = summary.key_points
        note.suggested_tags = summary.suggested_tags
        note.status, note.summary_error = "ready", None
        note.comment_score_error = result.comment_score_error
        note.updated_at = utcnow()
        # Preserve manual and previous tags; new suggestions are additive.
        for name in dict.fromkeys(" ".join(tag.split())[:50] for tag in summary.suggested_tags):
            if name:
                self.add_tag(note.id, name)
        # A scoring failure must not erase earlier valid scores.
        if result.comment_score_error is None:
            scores = {score.index: score for score in result.comment_scores}
            for position, comment in enumerate(self.comments(note.id)):
                score = scores.get(position)
                comment.ai_score = score.score if score else None
                comment.ai_reason = score.reason if score else None
                comment.is_valuable = (
                    score is not None and score.score >= result.comment_score_threshold
                )
        job.status, job.last_error = "success", result.comment_score_error
        job.execution_id = job.lease_expires_at = job.next_retry_at = None
