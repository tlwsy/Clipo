# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.base import utcnow
from app.models import ShortcutPairing
from app.repositories import UserRepository


class ShortcutRepository(UserRepository):
    def issue(
        self, identifier: str, code_hash: str, name: str, server_url: str, expires_at: datetime
    ) -> ShortcutPairing:
        values = dict(
            user_id=self.user_id,
            id=identifier,
            code_hash=code_hash,
            name=name,
            server_url=server_url,
            created_at=utcnow(),
            expires_at=expires_at,
            consumed_at=None,
            token_id=None,
        )
        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        self.db.execute(
            insert(ShortcutPairing)
            .values(**values)
            .on_conflict_do_update(index_elements=[ShortcutPairing.user_id], set_=values)
        )
        return self.get(identifier)

    def get(self, identifier: str) -> ShortcutPairing | None:
        return self.db.scalar(
            select(ShortcutPairing).where(
                ShortcutPairing.user_id == self.user_id, ShortcutPairing.id == identifier
            )
        )

    def cancel(self, identifier: str) -> bool:
        return (
            self.db.execute(
                delete(ShortcutPairing).where(
                    ShortcutPairing.user_id == self.user_id,
                    ShortcutPairing.id == identifier,
                    ShortcutPairing.consumed_at.is_(None),
                )
            ).rowcount
            == 1
        )

    def consume(self, code_hash: str) -> ShortcutPairing | None:
        # The credential and its expiry are checked in the atomic write, not only a prior read.
        return self.db.scalar(
            update(ShortcutPairing)
            .where(
                ShortcutPairing.user_id == self.user_id,
                ShortcutPairing.code_hash == code_hash,
                ShortcutPairing.consumed_at.is_(None),
                ShortcutPairing.expires_at > utcnow(),
            )
            .values(consumed_at=utcnow())
            .returning(ShortcutPairing)
        )
