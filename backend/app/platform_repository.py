"""Credential-bound login checks. Task arguments never contain credentials."""

import hashlib
import uuid
from datetime import timedelta

from sqlalchemy import and_, delete, or_, select, update

from app.db.base import utcnow
from app.errors import ClipoError
from app.models import PlatformCheck
from app.repositories import UserRepository
from app.schemas.settings import PlatformCheckResponse


class PlatformCheckRepository(UserRepository):
    def credential_hash(self, platform: str) -> str | None:
        encrypted = self.settings().platform_cookies.get(platform)
        return hashlib.sha256(encrypted.encode()).hexdigest() if encrypted else None

    def current(self, platform: str) -> PlatformCheck | None:
        return self.db.scalar(
            select(PlatformCheck).where(
                PlatformCheck.user_id == self.user_id,
                PlatformCheck.platform == platform,
                PlatformCheck.credential_hash == self.credential_hash(platform),
            )
        )

    def status(self, platform: str) -> PlatformCheckResponse:
        if not self.credential_hash(platform):
            return PlatformCheckResponse(status="unconfigured")
        row = self.current(platform)
        if row is None:
            return PlatformCheckResponse(status="unverified")
        return PlatformCheckResponse(
            status=row.status,
            message=row.message,
            requested_at=row.requested_at,
            checked_at=row.checked_at,
        )

    def clear(self, platform: str) -> None:
        self.db.execute(
            delete(PlatformCheck).where(
                PlatformCheck.user_id == self.user_id,
                PlatformCheck.platform == platform,
            )
        )

    def request(self, platform: str) -> PlatformCheck:
        digest = self.credential_hash(platform)
        if not digest:
            raise ClipoError(
                409, "cookie_not_configured", "请先保存该平台的 Cookie，再检测登录状态"
            )
        row = self.current(platform)
        if row is not None and row.status in ("queued", "running"):
            return row
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.bind.dialect.name == "sqlite" else pg_insert
        values = dict(
            request_id=uuid.uuid4().hex,
            credential_hash=digest,
            status="queued",
            attempts=0,
            message=None,
            requested_at=utcnow(),
            checked_at=None,
            lease_expires_at=None,
            execution_id=None,
        )
        statement = insert(PlatformCheck).values(user_id=self.user_id, platform=platform, **values)
        self.db.execute(
            statement.on_conflict_do_update(
                index_elements=["user_id", "platform"],
                set_=values,
            )
        )
        self.db.expire_all()
        row = self.current(platform)
        if row is None:
            raise ClipoError(409, "cookie_changed", "Cookie 已变更，请重新检测")
        return row

    def claim(self, platform: str, request_id: str, execution_id: str) -> bool:
        now = utcnow()
        result = self.db.execute(
            update(PlatformCheck)
            .where(
                PlatformCheck.user_id == self.user_id,
                PlatformCheck.platform == platform,
                PlatformCheck.request_id == request_id,
                PlatformCheck.credential_hash == self.credential_hash(platform),
                PlatformCheck.attempts < 3,
                or_(
                    PlatformCheck.status == "queued",
                    and_(
                        PlatformCheck.status == "running",
                        PlatformCheck.lease_expires_at <= now,
                    ),
                ),
            )
            .values(
                status="running",
                attempts=PlatformCheck.attempts + 1,
                execution_id=execution_id,
                lease_expires_at=now + timedelta(minutes=3),
            )
        )
        return result.rowcount == 1

    def finish(
        self,
        platform: str,
        request_id: str,
        execution_id: str,
        status: str,
        message: str,
    ) -> None:
        self.db.execute(
            update(PlatformCheck)
            .where(
                PlatformCheck.user_id == self.user_id,
                PlatformCheck.platform == platform,
                PlatformCheck.request_id == request_id,
                PlatformCheck.execution_id == execution_id,
                PlatformCheck.status == "running",
                PlatformCheck.credential_hash == self.credential_hash(platform),
            )
            .values(
                status=status,
                message=message,
                checked_at=utcnow(),
                execution_id=None,
                lease_expires_at=None,
            )
        )
