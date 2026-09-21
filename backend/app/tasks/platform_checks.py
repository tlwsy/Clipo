"""Persist, dispatch and recover credential checks without exposing secrets to Huey."""

import logging
import uuid

from huey import SqliteHuey
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.base import utcnow
from app.extractors.base import ExtractionError, LoginExpiredError
from app.extractors.xhs_api import XhsClient
from app.extractors.xiaoheihe import HeyboxClient
from app.models import PlatformCheck
from app.platform_repository import PlatformCheckRepository
from app.services.settings import load_platform_cookie

logger = logging.getLogger("clipo.platform_checks")


class PlatformCheckQueue:
    def __init__(
        self, huey: SqliteHuey, sessions: sessionmaker[Session], settings: Settings
    ) -> None:
        self.sessions = sessions
        self.settings = settings

        @huey.task(name="clipo.platform_check")
        def check(user_id: int, platform: str, request_id: str) -> None:
            self.run(user_id, platform, request_id)

        self.check = check

    def enqueue(self, user_id: int, platform: str, request_id: str) -> None:
        try:
            self.check(user_id, platform, request_id)
        except Exception:
            logger.error("Platform check dispatch failed; committed request will be recovered")

    def run(self, user_id: int, platform: str, request_id: str) -> None:
        execution_id = uuid.uuid4().hex
        with self.sessions.begin() as db:
            repository = PlatformCheckRepository(db, user_id)
            if not repository.claim(platform, request_id, execution_id):
                return
        try:
            with self.sessions() as db:
                repository = PlatformCheckRepository(db, user_id)
                row = repository.current(platform)
                if row is None or row.request_id != request_id:
                    return
                cookie = load_platform_cookie(repository, platform, self.settings)
            if cookie is None:
                return
            client = XhsClient(cookie) if platform == "xiaohongshu" else HeyboxClient(cookie)
            valid = client.check_login()
            status = "valid" if valid else "invalid"
            message = (
                "登录有效（以本次检测时间为准）"
                if valid
                else "登录态失效，请更新 Cookie 后重新检测"
            )
        except LoginExpiredError:
            status, message = "invalid", "登录态失效，请更新 Cookie 后重新检测"
        except Exception as exc:
            status = "error"
            message = (
                str(exc)
                if isinstance(exc, ExtractionError)
                else "暂时无法确认登录状态，请稍后重新检测"
            )
        with self.sessions.begin() as db:
            PlatformCheckRepository(db, user_id).finish(
                platform,
                request_id,
                execution_id,
                status,
                message,
            )

    def recover(self) -> None:
        now = utcnow()
        with self.sessions.begin() as db:
            db.execute(
                update(PlatformCheck)
                .where(
                    PlatformCheck.status == "running",
                    PlatformCheck.lease_expires_at <= now,
                    PlatformCheck.attempts >= 3,
                )
                .values(
                    status="error",
                    message="检测被中断，请重新检测",
                    checked_at=now,
                    execution_id=None,
                    lease_expires_at=None,
                )
            )
            # Global scan dispatches IDs only; all execution and results are user scoped.
            pending = list(
                db.execute(
                    select(
                        PlatformCheck.user_id,
                        PlatformCheck.platform,
                        PlatformCheck.request_id,
                    )
                    .where(
                        or_(
                            PlatformCheck.status == "queued",
                            and_(
                                PlatformCheck.status == "running",
                                PlatformCheck.lease_expires_at <= now,
                            ),
                        )
                    )
                    .order_by(PlatformCheck.requested_at)
                    .limit(100)
                )
            )
        for user_id, platform, request_id in pending:
            self.enqueue(user_id, platform, request_id)
