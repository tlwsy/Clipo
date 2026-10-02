# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint("block_index >= 0", name="annotation_block_index"),
        CheckConstraint("start_offset >= 0 AND end_offset > start_offset", name="annotation_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    block_index: Mapped[int]
    start_offset: Mapped[int]
    end_offset: Mapped[int]
    selected_text: Mapped[str] = mapped_column(Text)
    highlight_color: Mapped[str | None] = mapped_column(String(20))
    note_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
