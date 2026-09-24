# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime


class AccessBucket(Base):
    __tablename__ = "access_buckets"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    count: Mapped[int]
