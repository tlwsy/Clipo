# SPDX-License-Identifier: AGPL-3.0-or-later
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelUsage(Base):
    __tablename__ = "model_usage"
    __table_args__ = (CheckConstraint("calls >= 0", name="calls"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    calls: Mapped[int] = mapped_column(BigInteger, default=0)
