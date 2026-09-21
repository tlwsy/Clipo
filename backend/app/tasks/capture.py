import logging
import uuid

from huey import SqliteHuey, crontab
from pydantic import SecretStr
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.capture_repository import CaptureRepository
from app.config import Settings
from app.db.base import utcnow
from app.extractors.base import ExtractionError
from app.extractors.registry import ExtractorRegistry
from app.llm.client import CompatibleClient
from app.llm.orchestrator import SummaryResult, load_config, summarize
from app.models import CaptureJob
from app.services.settings import load_platform_cookie
from app.tasks.platform_checks import PlatformCheckQueue

logger = logging.getLogger("clipo.capture")
RETRY_DELAYS = (30, 120, 480)


class CapturePipeline:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        registry: ExtractorRegistry | None = None,
        llm: CompatibleClient | None = None,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.registry = registry
        self.llm = llm or CompatibleClient()

    def _cookie(self, user_id: int, platform: str) -> SecretStr | None:
        with self.sessions() as db:
            return load_platform_cookie(CaptureRepository(db, user_id), platform, self.settings)

    def run(self, user_id: int, job_id: str) -> int | None:
        execution_id = uuid.uuid4().hex
        with self.sessions.begin() as db:
            repository = CaptureRepository(db, user_id)
            job = repository.claim(job_id, execution_id)
            if job is None:
                return None
            url, attempts = job.url, job.attempts
        try:
            with self.sessions() as db:
                repository = CaptureRepository(db, user_id)
                max_comments = repository.capture_settings().max_comments
                content = repository.cache(url, max_comments=max_comments)
            cached = content is not None
            if content is None:
                registry = self.registry or ExtractorRegistry(
                    cookie_loader=lambda platform: self._cookie(user_id, platform),
                    max_comments=max_comments,
                )
                content = registry.get(url).extract(url)
                with self.sessions.begin() as db:
                    CaptureRepository(db, user_id).put_cache(
                        url, content, self.settings.extraction_cache_ttl_seconds
                    )
            try:
                with self.sessions() as db:
                    config = load_config(CaptureRepository(db, user_id), self.settings)
                result = summarize(content, config, self.llm)
            except Exception:
                result = SummaryResult(
                    None,
                    "未生成摘要：模型配置无法读取，请重新保存模型设置；原文已保存",
                    comment_score_error=(
                        "未生成评论评分：模型配置无法读取，请重新保存模型设置；已采集评论已保留"
                        if content.comments
                        else None
                    ),
                )
            with self.sessions.begin() as db:
                CaptureRepository(db, user_id).finish(job_id, execution_id, content, result, cached)
        except Exception as exc:
            message = (
                str(exc)
                if isinstance(exc, ExtractionError)
                else "处理暂时失败，请稍后重试；持续失败请联系管理员检查服务"
            )
            retryable = exc.retryable if isinstance(exc, ExtractionError) else True
            delay = (
                RETRY_DELAYS[attempts - 1] if retryable and attempts <= len(RETRY_DELAYS) else None
            )
            with self.sessions.begin() as db:
                CaptureRepository(db, user_id).fail(job_id, execution_id, message, delay)
            logger.warning(
                "Capture %s failed (%s), attempt %s", job_id, type(exc).__name__, attempts
            )
            return delay
        return None


class CaptureQueue:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings):
        settings.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.huey = SqliteHuey("clipo-captures", filename=str(settings.queue_path), results=False)
        self.sessions = sessions
        self.pipeline = CapturePipeline(sessions, settings)
        self.platform_checks = PlatformCheckQueue(self.huey, sessions, settings)

        @self.huey.task(name="clipo.capture")
        def capture(user_id: int, job_id: str):
            delay = self.pipeline.run(user_id, job_id)
            if delay is not None:
                capture.schedule(args=(user_id, job_id), delay=delay)

        self.capture = capture

        @self.huey.periodic_task(crontab(minute="*"), name="clipo.recover")
        def recover():
            self.recover()

    def enqueue(self, user_id: int, job_id: str):
        try:
            self.capture(user_id, job_id)
        except Exception:
            # The committed job is the outbox. The worker recovers missed dispatches.
            logger.error("Queue dispatch failed; job %s will be recovered", job_id)

    def recover(self):
        now = utcnow()
        with self.sessions.begin() as db:
            db.execute(
                update(CaptureJob)
                .where(
                    CaptureJob.status == "running",
                    CaptureJob.lease_expires_at <= now,
                    CaptureJob.attempts >= 4,
                )
                .values(
                    status="failed",
                    last_error="任务处理被中断，请点击重试",
                    lease_expires_at=None,
                    execution_id=None,
                    updated_at=now,
                )
            )
            # Global scans are only for dispatch; actual work always uses a user-scoped repository.
            pending = list(
                db.execute(
                    select(CaptureJob.user_id, CaptureJob.id)
                    .where(
                        or_(
                            CaptureJob.status == "queued",
                            and_(CaptureJob.status == "retrying", CaptureJob.next_retry_at <= now),
                            and_(
                                CaptureJob.status == "running", CaptureJob.lease_expires_at <= now
                            ),
                        )
                    )
                    .order_by(CaptureJob.updated_at)
                    .limit(100)
                )
            )
        for user_id, job_id in pending:
            self.enqueue(user_id, job_id)
        self.platform_checks.recover()
