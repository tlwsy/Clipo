# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, LargeBinary, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow
from app.models import json_type


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(40))
    origin_url: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    author_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))


class NoteTag(Base):
    __tablename__ = "notes_tags"

    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    content: Mapped[dict[str, Any]] = mapped_column(json_type)
    summary_markdown: Mapped[str | None] = mapped_column(Text)
    key_points: Mapped[list[str]] = mapped_column(json_type, default=list)
    suggested_tags: Mapped[list[str]] = mapped_column(json_type, default=list)
    status: Mapped[str] = mapped_column(String(32))
    is_favorite: Mapped[bool] = mapped_column(default=False, server_default=false())
    summary_error: Mapped[str | None] = mapped_column(Text)
    comment_score_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    author: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    likes: Mapped[int] = mapped_column(default=0)
    replies: Mapped[int] = mapped_column(default=0)
    position: Mapped[int]
    ai_score: Mapped[float | None]
    ai_reason: Mapped[str | None] = mapped_column(Text)
    is_valuable: Mapped[bool] = mapped_column(default=False, server_default=false())


class CaptureJob(Base):
    __tablename__ = "capture_jobs"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict[str, Any] | None] = mapped_column(json_type)
    request_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), index=True, default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    note_id: Mapped[int | None] = mapped_column(ForeignKey("notes.id", ondelete="SET NULL"))
    cached: Mapped[bool] = mapped_column(default=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    execution_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ExtractionCache(Base):
    __tablename__ = "extraction_cache"
    __table_args__ = (UniqueConstraint("user_id", "url_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    url_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict[str, Any]] = mapped_column(json_type)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class CaptureUpload(Base):
    __tablename__ = "capture_uploads"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("capture_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    total_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class CaptureUploadChunk(Base):
    __tablename__ = "capture_upload_chunks"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("capture_uploads.job_id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
