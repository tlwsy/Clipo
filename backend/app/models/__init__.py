from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow

json_type = JSON().with_variant(JSONB, "postgresql")


class InstanceState(Base):
    __tablename__ = "instance_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ShortcutPairing(Base):
    __tablename__ = "shortcut_pairings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(32), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    server_url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    token_id: Mapped[int | None] = mapped_column(ForeignKey("api_tokens.id", ondelete="SET NULL"))


class PlatformCheck(Base):
    __tablename__ = "platform_checks"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    platform: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(32))
    credential_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime)
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    execution_id: Mapped[str | None] = mapped_column(String(32))


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    llm_config: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)
    platform_cookies: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)
    capture_config: Mapped[dict[str, Any]] = mapped_column(
        json_type, default=dict, server_default="{}"
    )
    media_policy: Mapped[str] = mapped_column(String(32), default="thumbnail_only")
    backup_config: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)


# Import every mapped table so Alembic sees the complete metadata.
from app.models.backup import BackupJob  # noqa: E402, F401
from app.models.capture import (  # noqa: E402, F401
    CaptureJob,
    CaptureUpload,
    CaptureUploadChunk,
    Comment,
    ExtractionCache,
    Note,
    NoteTag,
    Source,
    Tag,
)
