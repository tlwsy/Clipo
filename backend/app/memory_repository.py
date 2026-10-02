# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime, timedelta

from sqlalchemy import case, delete, exists, func, or_, select, update

from app.db.base import utcnow
from app.errors import ClipoError
from app.models import Annotation, MemoryGalleryDismissal, Note, Source
from app.note_repository import NoteRepository
from app.schemas.memory import MemoryGallery, MemoryHistory, MemoryNote
from app.services.memory import sample_memories
from app.services.notes import note_excerpt, site_name


class MemoryGalleryRepository(NoteRepository):
    def gallery(self, count: int) -> MemoryGallery:
        now = utcnow()
        annotated = exists().where(
            Annotation.note_id == Note.id, Annotation.user_id == self.user_id
        )
        dismissed = exists().where(
            MemoryGalleryDismissal.note_id == Note.id,
            MemoryGalleryDismissal.user_id == self.user_id,
            MemoryGalleryDismissal.dismissed_at > now - timedelta(days=30),
        )
        candidates = self.db.execute(
            select(Note.id, Note.created_at)
            .where(
                Note.user_id == self.user_id,
                or_(Note.last_viewed_at.is_(None), Note.last_viewed_at <= now - timedelta(days=7)),
                or_(
                    annotated,
                    func.length(func.trim(func.coalesce(Note.summary_markdown, ""))) > 0,
                    Note.reading_duration_seconds > 120,
                ),
                ~dismissed,
            )
            .execution_options(yield_per=500)
        )
        ids = sample_memories(((row.id, row.created_at) for row in candidates), count, now)
        if not ids:
            return MemoryGallery(notes=[])
        annotation_count = (
            select(func.count(Annotation.id))
            .where(Annotation.note_id == Note.id, Annotation.user_id == self.user_id)
            .correlate(Note)
            .scalar_subquery()
        )
        rows = self.db.execute(
            select(Note, Source.platform, annotation_count)
            .join(Source, Source.id == Note.source_id)
            .where(Note.user_id == self.user_id, Source.user_id == self.user_id, Note.id.in_(ids))
        )
        notes = {
            note.id: MemoryNote(
                id=note.id,
                title=note.title,
                url=note.url,
                summary_snippet=note_excerpt(note),
                key_points=note.key_points[:5],
                platform=platform,
                site_name=site_name(note),
                created_at=note.created_at,
                annotations_count=annotations_count,
                has_summary=bool(note.summary_markdown and note.summary_markdown.strip()),
                is_favorite=note.is_favorite,
            )
            for note, platform, annotations_count in rows
        }
        return MemoryGallery(notes=[notes[note_id] for note_id in ids if note_id in notes])

    def record_view(self, note_id: int, duration_seconds: int) -> None:
        # SQL arithmetic avoids losing increments from concurrent tabs/devices. Reading
        # does not modify content timestamps or trigger a new semantic embedding.
        maximum = 2147483647
        result = self.db.execute(
            update(Note)
            .where(Note.id == note_id, Note.user_id == self.user_id)
            .values(
                last_viewed_at=utcnow(),
                reading_duration_seconds=case(
                    (Note.reading_duration_seconds > maximum - duration_seconds, maximum),
                    else_=Note.reading_duration_seconds + duration_seconds,
                ),
            )
        )
        if not result.rowcount:
            raise ClipoError(404, "note_not_found", "笔记不存在，请返回列表刷新")

    def dismiss(self, note_id: int, dismissed_at: datetime | None = None) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        self.note(note_id)
        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        stamp = dismissed_at or utcnow()
        self.db.execute(
            insert(MemoryGalleryDismissal)
            .values(note_id=note_id, user_id=self.user_id, dismissed_at=stamp)
            .on_conflict_do_update(
                index_elements=["note_id", "user_id"], set_={"dismissed_at": stamp}
            )
        )

    def history(self, note_id: int) -> MemoryHistory:
        note = self.note(note_id)
        dismissed_at = self.db.scalar(
            select(MemoryGalleryDismissal.dismissed_at).where(
                MemoryGalleryDismissal.note_id == note_id,
                MemoryGalleryDismissal.user_id == self.user_id,
            )
        )
        return MemoryHistory(
            last_viewed_at=note.last_viewed_at,
            reading_duration_seconds=note.reading_duration_seconds,
            memory_dismissed_at=dismissed_at,
        )

    def clear_expired(self, now: datetime) -> None:
        self.db.execute(
            delete(MemoryGalleryDismissal).where(
                MemoryGalleryDismissal.user_id == self.user_id,
                MemoryGalleryDismissal.dismissed_at <= now - timedelta(days=30),
            )
        )
