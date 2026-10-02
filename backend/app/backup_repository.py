# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from datetime import timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import utcnow
from app.errors import ClipoError
from app.memory_repository import MemoryGalleryRepository
from app.models import (
    Annotation,
    BackupJob,
    Collection,
    Comment,
    Note,
    NoteCollection,
    NoteTag,
    Source,
    Tag,
)
from app.note_repository import NoteRepository
from app.schemas.backup import Archive, ArchiveCollection, ArchiveCollectionMember


def due_jobs() -> ColumnElement[bool]:
    now = utcnow()
    return or_(
        BackupJob.status == "queued",
        and_(BackupJob.status == "retrying", BackupJob.next_retry_at <= now),
        and_(BackupJob.status == "running", BackupJob.lease_expires_at <= now),
    )


class BackupRepository(NoteRepository):
    def backup_job(self, job_id: str) -> BackupJob:
        job = self.db.scalar(
            select(BackupJob).where(BackupJob.user_id == self.user_id, BackupJob.id == job_id)
        )
        if job is None:
            raise ClipoError(404, "backup_not_found", "备份任务不存在，请刷新列表")
        return job

    def backup_jobs(self) -> list[BackupJob]:
        return list(
            self.db.scalars(
                select(BackupJob)
                .where(BackupJob.user_id == self.user_id)
                .order_by(BackupJob.created_at.desc())
                .limit(50)
            )
        )

    def create_backup_job(self, kind: str, key: str) -> BackupJob:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        self.db.execute(
            insert(BackupJob)
            .values(id=uuid.uuid4().hex, user_id=self.user_id, kind=kind, request_key=key)
            .on_conflict_do_nothing(index_elements=["user_id", "request_key"])
        )
        job = self.db.scalar(
            select(BackupJob).where(BackupJob.user_id == self.user_id, BackupJob.request_key == key)
        )
        assert job is not None
        return job

    def claim_backup(self, job_id: str, execution: str) -> BackupJob | None:
        result = self.db.execute(
            update(BackupJob)
            .where(
                BackupJob.user_id == self.user_id,
                BackupJob.id == job_id,
                due_jobs(),
                BackupJob.attempts < 4,
            )
            .values(
                status="running",
                execution_id=execution,
                attempts=BackupJob.attempts + 1,
                next_retry_at=None,
                lease_expires_at=utcnow() + timedelta(hours=1),
                updated_at=utcnow(),
            )
        )
        return self.backup_job(job_id) if result.rowcount == 1 else None

    def fence_backup(self, job_id: str, execution: str, **values: object) -> bool:
        return (
            self.db.execute(
                update(BackupJob)
                .where(
                    BackupJob.user_id == self.user_id,
                    BackupJob.id == job_id,
                    BackupJob.status == "running",
                    BackupJob.execution_id == execution,
                )
                .values(updated_at=utcnow(), **values)
            ).rowcount
            == 1
        )

    def retry_backup(self, job_id: str) -> BackupJob:
        job = self.backup_job(job_id)
        if job.status != "failed":
            raise ClipoError(409, "backup_not_failed", "只有失败任务可以重试")
        self.db.execute(
            update(BackupJob)
            .where(
                BackupJob.user_id == self.user_id,
                BackupJob.id == job_id,
                BackupJob.status == "failed",
            )
            .values(status="queued", attempts=0, last_error=None, execution_id=None)
        )
        self.db.expire_all()
        return self.backup_job(job_id)

    def note_ids(self) -> list[int]:
        return list(
            self.db.scalars(select(Note.id).where(Note.user_id == self.user_id).order_by(Note.id))
        )

    def archive_collections(self) -> list[ArchiveCollection]:
        collections = list(
            self.db.scalars(
                select(Collection).where(Collection.user_id == self.user_id).order_by(Collection.id)
            )
        )
        members: dict[int, list[ArchiveCollectionMember]] = {row.id: [] for row in collections}
        links = self.db.scalars(
            select(NoteCollection)
            .join(Collection, Collection.id == NoteCollection.collection_id)
            .join(Note, Note.id == NoteCollection.note_id)
            .where(Collection.user_id == self.user_id, Note.user_id == self.user_id)
            .order_by(NoteCollection.collection_id, NoteCollection.note_id)
        )
        for link in links:
            members[link.collection_id].append(
                ArchiveCollectionMember(note_id=link.note_id, added_at=link.added_at)
            )
        return [
            ArchiveCollection(
                name=row.name,
                color=row.color,
                icon=row.icon,
                created_at=row.created_at,
                updated_at=row.updated_at,
                members=members[row.id],
            )
            for row in collections
        ]

    def restore(self, archive: Archive) -> int:
        # One transaction owns all imported rows. Original database identifiers never escape.
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        for tag in archive.tags:
            self.db.execute(
                insert(Tag)
                .values(user_id=self.user_id, name=tag.name)
                .on_conflict_do_nothing(index_elements=["user_id", "name"])
            )
        tags = {tag.name: tag.id for tag in self.list_tags()}
        restored_ids: dict[int, int] = {}
        for saved in archive.notes:
            source = Source(user_id=self.user_id, **saved.source.model_dump(exclude={"site_name"}))
            self.db.add(source)
            self.db.flush()
            values = saved.model_dump(
                exclude={
                    "id",
                    "source",
                    "comments",
                    "tags",
                    "content",
                    "annotations",
                    "reading_preferences",
                    "display_overrides",
                    "memory_dismissed_at",
                }
            )
            note = Note(
                user_id=self.user_id,
                source_id=source.id,
                content=saved.content.model_dump(mode="json"),
                display_overrides=saved.display_overrides.model_dump(exclude_none=True),
                **values,
            )
            self.db.add(note)
            self.db.flush()
            from app.embedding_repository import EmbeddingRepository

            EmbeddingRepository(self.db, self.user_id).invalidate_note(note)
            restored_ids[saved.id] = note.id
            if saved.memory_dismissed_at:
                MemoryGalleryRepository(self.db, self.user_id).dismiss(
                    note.id, saved.memory_dismissed_at
                )
            for annotation in saved.annotations:
                self.db.add(
                    Annotation(
                        note_id=note.id,
                        user_id=self.user_id,
                        **annotation.model_dump(exclude={"id"}),
                    )
                )
            for comment in saved.comments:
                self.db.add(Comment(note_id=note.id, **comment.model_dump(exclude={"id"})))
            for name in {tag.name for tag in saved.tags}:
                self.db.add(NoteTag(note_id=note.id, tag_id=tags[name]))
        for saved_collection in archive.collections:
            self.db.execute(
                insert(Collection)
                .values(user_id=self.user_id, **saved_collection.model_dump(exclude={"members"}))
                .on_conflict_do_nothing(index_elements=["user_id", "name"])
            )
            collection = self.db.scalar(
                select(Collection).where(
                    Collection.user_id == self.user_id, Collection.name == saved_collection.name
                )
            )
            assert collection is not None
            for member in saved_collection.members:
                self.db.add(
                    NoteCollection(
                        collection_id=collection.id,
                        note_id=restored_ids[member.note_id],
                        added_at=member.added_at,
                    )
                )
        # Append imports preserve the destination account's configured reading style.
        settings = self.settings()
        if not settings.reading_preferences:
            settings.reading_preferences = archive.reading_preferences.model_dump(exclude_none=True)
        return len(archive.notes)
