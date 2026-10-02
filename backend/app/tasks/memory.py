# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import timedelta

from huey import SqliteHuey, crontab
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import utcnow
from app.memory_repository import MemoryGalleryRepository
from app.models import MemoryGalleryDismissal


class MemoryMaintenance:
    def __init__(self, huey: SqliteHuey, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

        @huey.periodic_task(crontab(hour="3", minute="0"), name="clipo.memory.cleanup")
        def cleanup() -> None:
            self.cleanup()

    def cleanup(self) -> None:
        now = utcnow()
        last_user = 0
        while True:
            # This global scan discovers owners only; deletion remains user scoped.
            with self.sessions() as db:
                owners = list(
                    db.scalars(
                        select(MemoryGalleryDismissal.user_id)
                        .distinct()
                        .where(
                            MemoryGalleryDismissal.user_id > last_user,
                            MemoryGalleryDismissal.dismissed_at <= now - timedelta(days=30),
                        )
                        .order_by(MemoryGalleryDismissal.user_id)
                        .limit(100)
                    )
                )
            if not owners:
                return
            for user_id in owners:
                with self.sessions.begin() as db:
                    MemoryGalleryRepository(db, user_id).clear_expired(now)
            last_user = owners[-1]
