# SPDX-License-Identifier: AGPL-3.0-or-later
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.db.base import utcnow
from app.errors import ClipoError
from app.models import Collection, Note, NoteCollection
from app.note_repository import NoteRepository
from app.schemas.collection import CollectionCreate, CollectionResponse, CollectionUpdate


class CollectionRepository(NoteRepository):
    def collection(self, collection_id: int, *, lock: bool = False) -> Collection:
        query = select(Collection).where(
            Collection.id == collection_id, Collection.user_id == self.user_id
        )
        if lock:
            query = query.with_for_update()
        row = self.db.scalar(query)
        if row is None:
            raise ClipoError(404, "collection_not_found", "空间不存在，请刷新空间列表")
        return row

    def list_collections(self, note_id: int | None = None) -> list[CollectionResponse]:
        if note_id is not None:
            self.note(note_id)
        counts = (
            select(NoteCollection.collection_id, func.count().label("total"))
            .join(Note, Note.id == NoteCollection.note_id)
            .where(Note.user_id == self.user_id)
            .group_by(NoteCollection.collection_id)
            .subquery()
        )
        query = (
            select(Collection, func.coalesce(counts.c.total, 0))
            .outerjoin(counts, counts.c.collection_id == Collection.id)
            .where(Collection.user_id == self.user_id)
            .order_by(Collection.created_at, Collection.id)
        )
        if note_id is not None:
            query = query.where(
                Collection.id.in_(
                    select(NoteCollection.collection_id).where(NoteCollection.note_id == note_id)
                )
            )
        return [self.response(row, count) for row, count in self.db.execute(query)]

    def response(self, row: Collection, count: int | None = None) -> CollectionResponse:
        if count is None:
            count = (
                self.db.scalar(
                    select(func.count())
                    .select_from(NoteCollection)
                    .join(Note, Note.id == NoteCollection.note_id)
                    .join(Collection, Collection.id == NoteCollection.collection_id)
                    .where(
                        Collection.id == row.id,
                        Collection.user_id == self.user_id,
                        Note.user_id == self.user_id,
                    )
                )
                or 0
            )
        return CollectionResponse(
            id=row.id,
            name=row.name,
            color=row.color,
            icon=row.icon,
            note_count=count,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def save(
        self, payload: CollectionCreate | CollectionUpdate, collection_id: int | None = None
    ) -> CollectionResponse:
        row = (
            self.collection(collection_id, lock=True)
            if collection_id is not None
            else Collection(user_id=self.user_id)
        )
        try:
            with self.db.begin_nested():
                for key, value in payload.model_dump(exclude_unset=True).items():
                    setattr(row, key, value)
                row.updated_at = utcnow()
                self.db.add(row)
                self.db.flush()
        except IntegrityError as exc:
            raise ClipoError(409, "collection_name_exists", "已有同名空间，请换一个名称") from exc
        return self.response(row)

    def delete_collection(self, collection_id: int) -> None:
        self.db.delete(self.collection(collection_id, lock=True))
        self.db.flush()

    def change_notes(
        self, collection_id: int, note_ids: list[int], *, remove: bool = False
    ) -> None:
        row = self.collection(collection_id, lock=True)
        identifiers = set(note_ids)
        owned = set(
            self.db.scalars(
                select(Note.id)
                .where(Note.user_id == self.user_id, Note.id.in_(identifiers))
                .with_for_update()
            )
        )
        if owned != identifiers:
            raise ClipoError(404, "note_not_found", "部分笔记不存在，请刷新后重试")
        if remove:
            self.db.execute(
                delete(NoteCollection).where(
                    NoteCollection.collection_id == row.id, NoteCollection.note_id.in_(owned)
                )
            )
        else:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
            self.db.execute(
                insert(NoteCollection)
                .values(
                    [
                        {"note_id": identifier, "collection_id": row.id}
                        for identifier in sorted(owned)
                    ]
                )
                .on_conflict_do_nothing()
            )
        row.updated_at = utcnow()
