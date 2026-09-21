from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import ApiToken, InstanceState, RefreshToken, User, UserSettings


class IdentityRepository:
    """Global lookups are restricted to authentication and instance initialization."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def setup_completed(self) -> bool:
        return bool(
            self.db.scalar(select(InstanceState.setup_completed).where(InstanceState.id == 1))
        )

    def claim_setup(self) -> bool:
        claimed = self.db.execute(
            update(InstanceState)
            .where(InstanceState.id == 1, InstanceState.setup_completed.is_(False))
            .values(setup_completed=True)
        )
        return claimed.rowcount == 1

    def by_username(self, username: str) -> User | None:
        return self.db.scalar(select(User).where(User.username == username))

    def by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def create_user(self, username: str, email: str, password_hash: str, is_admin: bool) -> User:
        user = User(username=username, email=email, password_hash=password_hash, is_admin=is_admin)
        self.db.add(user)
        self.db.flush()
        self.db.add(UserSettings(user_id=user.id))
        self.db.flush()
        return user

    def add_refresh(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        self.db.add(RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at))

    def consume_refresh(self, token_hash: str) -> int | None:
        # The conditional UPDATE is atomic on PostgreSQL and SQLite: only one request wins.
        return self.db.scalar(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > utcnow(),
            )
            .values(revoked_at=utcnow())
            .returning(RefreshToken.user_id)
        )

    def revoke_refresh(self, token_hash: str) -> None:
        self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    def authenticate_api_token(self, token_hash: str) -> User | None:
        token = self.db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash))
        if token is None:
            return None
        token.last_used_at = utcnow()
        return self.by_id(token.user_id)


class UserRepository:
    """All user-owned queries enforce the authenticated user's scope here."""

    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def settings(self) -> UserSettings:
        settings = self.db.get(UserSettings, self.user_id)
        if settings is None:
            raise RuntimeError("Missing user settings; check database migrations")
        return settings

    def set_llm(self, config: dict[str, Any]) -> None:
        self.settings().llm_config = config

    def set_platform_cookies(self, cookies: dict[str, str]) -> None:
        self.settings().platform_cookies = cookies

    def set_capture_config(self, config: dict[str, Any]) -> None:
        self.settings().capture_config = config

    def list_tokens(self) -> list[ApiToken]:
        return list(
            self.db.scalars(
                select(ApiToken)
                .where(ApiToken.user_id == self.user_id)
                .order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
            )
        )

    def create_token(self, name: str, token_hash: str) -> ApiToken:
        token = ApiToken(user_id=self.user_id, name=name, token_hash=token_hash)
        self.db.add(token)
        self.db.flush()
        return token

    def delete_token(self, token_id: int) -> bool:
        result = self.db.execute(
            delete(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == self.user_id)
        )
        return result.rowcount == 1
