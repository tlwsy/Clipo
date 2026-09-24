# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import hmac
import math
from datetime import timedelta

from sqlalchemy import case, delete, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import utcnow
from app.errors import ClipoError
from app.models import AccessBucket

PUBLIC_GLOBAL_LIMIT = 600
PUBLIC_CLIENT_LIMIT = 60
SUMMARY_LIMIT = 6
SHARE_LIMIT = 10
WINDOW_SECONDS = 60


class NoteRateLimiter:
    """Atomic shared counters; never persist raw IPs, user IDs or share tokens."""

    def __init__(self, sessions: sessionmaker[Session], secret: str) -> None:
        self.sessions = sessions
        self.secret = secret.encode()

    def consume(self, limits: list[tuple[str, int]]) -> None:
        now = utcnow()
        retry_after = None
        with self.sessions.begin() as db:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
            # Only recent bounded-window state remains, including when no worker is running.
            db.execute(delete(AccessBucket).where(AccessBucket.expires_at <= now))
            for subject, limit in limits:
                key = hmac.new(self.secret, subject.encode(), hashlib.sha256).hexdigest()
                expired = AccessBucket.expires_at <= now
                expires = now + timedelta(seconds=WINDOW_SECONDS)
                statement = insert(AccessBucket).values(key=key, expires_at=expires, count=1)
                allowed = db.scalar(
                    statement.on_conflict_do_update(
                        index_elements=["key"],
                        set_={
                            "expires_at": case((expired, expires), else_=AccessBucket.expires_at),
                            "count": case((expired, 1), else_=AccessBucket.count + 1),
                        },
                        where=or_(expired, AccessBucket.count < limit),
                    ).returning(AccessBucket.key)
                )
                if allowed is None:
                    deadline = db.scalar(
                        select(AccessBucket.expires_at).where(AccessBucket.key == key)
                    )
                    retry_after = (
                        max(1, math.ceil((deadline - now).total_seconds()))
                        if deadline
                        else WINDOW_SECONDS
                    )
                    break
        # Rejections and downstream validation failures must not roll back counted attempts.
        if retry_after is not None:
            raise ClipoError(
                429,
                "rate_limited",
                f"请求过于频繁，请在 {retry_after} 秒后重试",
                {"retry_after": retry_after},
            )

    def public_read(self, address: str) -> None:
        # Global first bounds both expensive reads and distinct address bucket growth.
        self.consume(
            [
                ("public:global", PUBLIC_GLOBAL_LIMIT),
                (f"public:address:{address}", PUBLIC_CLIENT_LIMIT),
            ]
        )

    def summary(self, user_id: int) -> None:
        self.consume([(f"summary:user:{user_id}", SUMMARY_LIMIT)])

    def share(self, user_id: int) -> None:
        self.consume([(f"share:user:{user_id}", SHARE_LIMIT)])
