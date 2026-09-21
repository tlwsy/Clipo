import base64
import hashlib
import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.db.base import utcnow
from app.errors import ClipoError
from app.extractors.base import CapturedContent
from app.llm.orchestrator import SummaryResult
from app.models import CaptureJob, Comment, ExtractionCache, Note, Source
from app.repositories import UserRepository
from app.schemas.settings import CaptureSettingsResponse


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def encode_cursor(item) -> str:
    return base64.urlsafe_b64encode(
        json.dumps([item.created_at.isoformat(), item.id]).encode()
    ).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str | int]:
    try:
        stamp, identifier = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        date = datetime.fromisoformat(stamp)
        if date.tzinfo is None or not isinstance(identifier, (int, str)):
            raise ValueError()
        return date, identifier
    except (ValueError, TypeError, KeyError) as exc:
        raise ClipoError(422, "invalid_cursor", "分页游标无效，请从第一页重新加载") from exc


class CaptureRepository(UserRepository):
    def job(self, job_id: str) -> CaptureJob:
        job = self.db.scalar(
            select(CaptureJob).where(CaptureJob.id == job_id, CaptureJob.user_id == self.user_id)
        )
        if job is None:
            raise ClipoError(404, "job_not_found", "任务不存在，请刷新保存队列")
        return job

    def create_job(self, url: str, key: str | None) -> CaptureJob:
        if key:
            existing = self.db.scalar(
                select(CaptureJob).where(
                    CaptureJob.user_id == self.user_id, CaptureJob.idempotency_key == key
                )
            )
            if existing:
                if existing.url != url:
                    raise ClipoError(
                        409,
                        "idempotency_conflict",
                        "此幂等键已用于其他链接，请更换 Idempotency-Key",
                    )
                return existing
        job = CaptureJob(
            id="j_" + uuid.uuid4().hex,
            user_id=self.user_id,
            url=url,
            idempotency_key=key,
            cached=self.cache(url) is not None,
        )
        try:
            with self.db.begin_nested():
                self.db.add(job)
                self.db.flush()
        except IntegrityError:
            if not key:
                raise
            return self.create_job(url, key)
        return job

    def page(self, model, cursor: str | None, limit: int, statuses: list[str] | None = None):
        query = select(model).where(model.user_id == self.user_id)
        if statuses:
            query = query.where(model.status.in_(statuses))
        if cursor:
            created, identifier = decode_cursor(cursor)
            if (model is Note and type(identifier) is not int) or (
                model is CaptureJob and not isinstance(identifier, str)
            ):
                raise ClipoError(422, "invalid_cursor", "分页游标不匹配，请从第一页重新加载")
            query = query.where(
                or_(
                    model.created_at < created,
                    and_(model.created_at == created, model.id < identifier),
                )
            )
        rows = list(
            self.db.scalars(
                query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
            )
        )
        return rows[:limit], encode_cursor(rows[limit - 1]) if len(rows) > limit else None

    def retry(self, job_id: str) -> CaptureJob:
        self.job(job_id)
        result = self.db.execute(
            update(CaptureJob)
            .where(
                CaptureJob.id == job_id,
                CaptureJob.user_id == self.user_id,
                CaptureJob.status == "failed",
            )
            .values(
                status="queued",
                attempts=0,
                last_error=None,
                next_retry_at=None,
                lease_expires_at=None,
                execution_id=None,
                updated_at=utcnow(),
            )
        )
        if result.rowcount != 1:
            raise ClipoError(409, "job_not_failed", "只有失败任务可以重试，请刷新队列查看最新状态")
        self.db.expire_all()
        return self.job(job_id)

    def claim(self, job_id: str, execution_id: str) -> CaptureJob | None:
        now = utcnow()
        result = self.db.execute(
            update(CaptureJob)
            .where(
                CaptureJob.id == job_id,
                CaptureJob.user_id == self.user_id,
                or_(
                    CaptureJob.status == "queued",
                    and_(CaptureJob.status == "retrying", CaptureJob.next_retry_at <= now),
                    and_(CaptureJob.status == "running", CaptureJob.lease_expires_at <= now),
                ),
                CaptureJob.attempts < 4,
            )
            .values(
                status="running",
                attempts=CaptureJob.attempts + 1,
                execution_id=execution_id,
                lease_expires_at=now + timedelta(minutes=10),
                next_retry_at=None,
                updated_at=now,
            )
        )
        return self.job(job_id) if result.rowcount == 1 else None

    def fail(self, job_id: str, execution_id: str, message: str, delay: int | None):
        self.db.execute(
            update(CaptureJob)
            .where(
                CaptureJob.id == job_id,
                CaptureJob.user_id == self.user_id,
                CaptureJob.execution_id == execution_id,
                CaptureJob.status == "running",
            )
            .values(
                status="retrying" if delay is not None else "failed",
                last_error=message,
                next_retry_at=utcnow() + timedelta(seconds=delay) if delay is not None else None,
                lease_expires_at=None,
                execution_id=None,
                updated_at=utcnow(),
            )
        )

    def capture_settings(self) -> CaptureSettingsResponse:
        return CaptureSettingsResponse.model_validate(self.settings().capture_config)

    def cache(self, url: str, *, max_comments: int | None = None) -> CapturedContent | None:
        row = self.db.scalar(
            select(ExtractionCache).where(
                ExtractionCache.user_id == self.user_id,
                ExtractionCache.url_hash == url_hash(url),
                ExtractionCache.expires_at > utcnow(),
            )
        )
        if row is None:
            return None
        content = CapturedContent.model_validate(row.content)
        if content.platform == "xiaohongshu":
            limit = self.capture_settings().max_comments if max_comments is None else max_comments
            # Legacy XHS cache entries were extracted with the fixed 100-comment ceiling.
            cached_limit = content.comment_capture_limit
            if limit > (100 if cached_limit is None else cached_limit):
                return None
            # Trim only the returned copy; retain the wider cache for later captures.
            content = content.model_copy(
                update={"comments": content.comments[:limit], "comment_capture_limit": limit}
            )
        return content

    def put_cache(self, url: str, content: CapturedContent, ttl: int):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.bind.dialect.name == "sqlite" else pg_insert
        statement = insert(ExtractionCache).values(
            user_id=self.user_id,
            url_hash=url_hash(url),
            content=content.model_dump(mode="json"),
            expires_at=utcnow() + timedelta(seconds=ttl),
        )
        self.db.execute(
            statement.on_conflict_do_update(
                index_elements=["user_id", "url_hash"],
                set_={
                    "content": statement.excluded.content,
                    "expires_at": statement.excluded.expires_at,
                },
            )
        )
        self.db.execute(
            delete(ExtractionCache).where(
                ExtractionCache.user_id == self.user_id, ExtractionCache.expires_at <= utcnow()
            )
        )

    def finish(
        self,
        job_id: str,
        execution_id: str,
        content: CapturedContent,
        result: SummaryResult,
        cached: bool,
    ) -> None:
        # Fence stale workers and lock the job until note creation and success commit together.
        claimed = self.db.execute(
            update(CaptureJob)
            .where(
                CaptureJob.id == job_id,
                CaptureJob.user_id == self.user_id,
                CaptureJob.status == "running",
                CaptureJob.execution_id == execution_id,
            )
            .values(updated_at=utcnow())
        )
        if claimed.rowcount != 1:
            return
        job = self.job(job_id)
        source = Source(
            user_id=self.user_id,
            platform=content.platform,
            origin_url=content.url,
            author=content.author,
            author_url=content.author_url,
            published_at=content.published_at,
        )
        self.db.add(source)
        self.db.flush()
        summary = result.summary
        note = Note(
            user_id=self.user_id,
            source_id=source.id,
            title=content.title,
            url=job.url,
            content=content.model_dump(mode="json"),
            summary_markdown=summary.summary_markdown if summary else None,
            key_points=summary.key_points if summary else [],
            suggested_tags=summary.suggested_tags if summary else [],
            status="ready" if summary else "original_only",
            summary_error=result.error,
            comment_score_error=result.comment_score_error,
        )
        self.db.add(note)
        self.db.flush()
        scores = {score.index: score for score in result.comment_scores}
        for position, comment in enumerate(content.comments):
            score = scores.get(position)
            self.db.add(
                Comment(
                    note_id=note.id,
                    position=position,
                    **comment.model_dump(),
                    ai_score=score.score if score else None,
                    ai_reason=score.reason if score else None,
                    is_valuable=score is not None and score.score >= result.comment_score_threshold,
                )
            )
        job.note_id, job.status, job.cached = note.id, "success", cached
        job.last_error = job.next_retry_at = job.lease_expires_at = job.execution_id = None

    def note(self, note_id: int) -> Note:
        note = self.db.scalar(select(Note).where(Note.id == note_id, Note.user_id == self.user_id))
        if note is None:
            raise ClipoError(404, "note_not_found", "笔记不存在或已删除，请返回笔记列表")
        return note

    def source(self, note: Note) -> Source:
        return self.db.scalar(
            select(Source).where(Source.id == note.source_id, Source.user_id == self.user_id)
        )

    def comments(self, note_id: int) -> list[Comment]:
        self.note(note_id)
        return list(
            self.db.scalars(
                select(Comment)
                .join(Note)
                .where(Note.user_id == self.user_id, Note.id == note_id)
                .order_by(Comment.position)
            )
        )

    def delete_note(self, note_id: int):
        note = self.note(note_id)
        # FK cascades remove the note/comments; completed jobs retain history with note_id=NULL.
        self.db.execute(
            delete(Source).where(Source.id == note.source_id, Source.user_id == self.user_id)
        )
