# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class NoteConversation(Base):
    __tablename__ = "note_conversations"
    __table_args__ = (
        UniqueConstraint("note_id", "turn_index", "role"),
        CheckConstraint("turn_index >= 0", name="turn_index"),
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        Index("ix_note_conversations_note_turn", "note_id", "turn_index"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    turn_index: Mapped[int]
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ConversationJob(Base):
    __tablename__ = "conversation_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key"),
        UniqueConstraint("note_id", "turn_index"),
        Index(
            "uq_conversation_jobs_active_note",
            "user_id",
            "note_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running', 'retrying')"),
            postgresql_where=text("status IN ('queued', 'running', 'retrying')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    turn_index: Mapped[int]
    request_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    execution_id: Mapped[str | None] = mapped_column(String(32))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
