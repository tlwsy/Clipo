# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.errors import ClipoError
from app.models import Note, SharedLink
from app.note_repository import NoteRepository
from app.security.credentials import hash_token


class SharingRepository(NoteRepository):
    def list_shares(self, note_id: int) -> list[SharedLink]:
        self.note(note_id)
        return list(
            self.db.scalars(
                select(SharedLink)
                .where(
                    SharedLink.user_id == self.user_id,
                    SharedLink.note_id == note_id,
                    SharedLink.revoked_at.is_(None),
                    or_(SharedLink.expires_at.is_(None), SharedLink.expires_at > utcnow()),
                )
                .order_by(SharedLink.created_at.desc(), SharedLink.id.desc())
            )
        )

    def create_share(self, note_id: int, days: int | None) -> tuple[SharedLink, str]:
        locked = self.db.execute(
            update(Note)
            .where(Note.id == note_id, Note.user_id == self.user_id)
            .values(updated_at=Note.updated_at)
        )
        if locked.rowcount != 1:
            raise ClipoError(404, "note_not_found", "笔记不存在或已删除，请返回笔记列表")
        # Bound retained capabilities per note; historical links cannot become valid again.
        self.db.execute(
            delete(SharedLink).where(
                SharedLink.user_id == self.user_id,
                SharedLink.note_id == note_id,
                or_(SharedLink.revoked_at.is_not(None), SharedLink.expires_at <= utcnow()),
            )
        )
        count = self.db.scalar(
            select(func.count())
            .select_from(SharedLink)
            .where(SharedLink.user_id == self.user_id, SharedLink.note_id == note_id)
        )
        if count is not None and count >= 10:
            raise ClipoError(409, "share_limit", "每篇笔记最多保留 10 个有效链接，请先撤销旧链接")
        token = secrets.token_urlsafe(32)
        link = SharedLink(
            id=uuid.uuid4().hex,
            user_id=self.user_id,
            note_id=note_id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(days=days) if days is not None else None,
        )
        self.db.add(link)
        self.db.flush()
        return link, token

    def revoke_share(self, note_id: int, share_id: str) -> None:
        self.note(note_id)
        result = self.db.execute(
            update(SharedLink)
            .where(
                SharedLink.id == share_id,
                SharedLink.user_id == self.user_id,
                SharedLink.note_id == note_id,
            )
            .values(revoked_at=utcnow())
        )
        if result.rowcount != 1:
            raise ClipoError(404, "share_not_found", "分享链接不存在，请刷新笔记")


def resolve_share(db: Session, token: str) -> tuple[SharingRepository, int]:
    # This is the sole anonymous capability lookup; subsequent reads are user-scoped.
    row = db.scalar(
        select(SharedLink)
        .join(Note, Note.id == SharedLink.note_id)
        .where(
            SharedLink.token_hash == hash_token(token),
            SharedLink.revoked_at.is_(None),
            Note.user_id == SharedLink.user_id,
            or_(SharedLink.expires_at.is_(None), SharedLink.expires_at > utcnow()),
        )
    )
    if row is None:
        raise ClipoError(404, "share_unavailable", "分享链接无效、已过期或已撤销，请联系分享者")
    return SharingRepository(db, row.user_id), row.note_id
