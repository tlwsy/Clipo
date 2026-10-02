# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class EmbeddingJob(Base):
    """Durable outbox for note vectors, short-lived query vectors and bounded backfills."""

    __tablename__ = "embedding_jobs"
    __table_args__ = (UniqueConstraint("user_id", "target_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_key: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    note_id: Mapped[int | None] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    config_key: Mapped[str] = mapped_column(String(64), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    input_text: Mapped[str | None] = mapped_column(Text)
    vector: Mapped[list[float] | None] = mapped_column(JSON(none_as_null=True), deferred=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    execution_id: Mapped[str | None] = mapped_column(String(32))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cursor: Mapped[int] = mapped_column(default=0)
    through_id: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
