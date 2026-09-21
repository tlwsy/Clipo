from sqlalchemy import and_, delete, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.capture_repository import CaptureRepository, decode_cursor, encode_cursor
from app.db.base import utcnow
from app.errors import ClipoError
from app.models import Note, NoteTag, Tag


class NoteRepository(CaptureRepository):
    def list_tags(self) -> list[Tag]:
        return list(
            self.db.scalars(
                select(Tag).where(Tag.user_id == self.user_id).order_by(Tag.name, Tag.id)
            )
        )

    def tags_for(self, note_ids: list[int]) -> dict[int, list[Tag]]:
        result: dict[int, list[Tag]] = {identifier: [] for identifier in note_ids}
        rows = self.db.execute(
            select(NoteTag.note_id, Tag)
            .join(Tag, Tag.id == NoteTag.tag_id)
            .join(Note, Note.id == NoteTag.note_id)
            .where(Note.user_id == self.user_id, Tag.user_id == self.user_id, Note.id.in_(note_ids))
            .order_by(Tag.name, Tag.id)
        )
        for note_id, tag in rows:
            result[note_id].append(tag)
        return result

    def add_tag(self, note_id: int, name: str) -> Tag:
        note = self.note(note_id)
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        self.db.execute(
            insert(Tag)
            .values(user_id=self.user_id, name=name)
            .on_conflict_do_nothing(index_elements=["user_id", "name"])
        )
        tag = self.db.scalar(select(Tag).where(Tag.user_id == self.user_id, Tag.name == name))
        assert tag is not None
        self.db.execute(
            insert(NoteTag).values(note_id=note.id, tag_id=tag.id).on_conflict_do_nothing()
        )
        note.updated_at = utcnow()
        return tag

    def remove_tag(self, note_id: int, tag_id: int) -> None:
        note = self.note(note_id)
        tag_ids = select(Tag.id).where(Tag.user_id == self.user_id, Tag.id == tag_id)
        self.db.execute(
            delete(NoteTag).where(NoteTag.note_id == note.id, NoteTag.tag_id.in_(tag_ids))
        )
        note.updated_at = utcnow()

    def delete_tag(self, tag_id: int) -> None:
        result = self.db.execute(delete(Tag).where(Tag.id == tag_id, Tag.user_id == self.user_id))
        if not result.rowcount:
            raise ClipoError(404, "tag_not_found", "标签不存在，请刷新标签列表")

    def favorite(self, note_id: int, value: bool) -> None:
        note = self.note(note_id)
        note.is_favorite = value
        note.updated_at = utcnow()

    def list_notes(
        self,
        cursor: str | None,
        limit: int,
        tag_id: int | None = None,
        favorite: bool | None = None,
        search: ColumnElement[bool] | None = None,
    ) -> tuple[list[Note], str | None]:
        query = select(Note).where(Note.user_id == self.user_id)
        if tag_id is not None:
            query = query.where(
                Note.id.in_(
                    select(NoteTag.note_id)
                    .join(Tag)
                    .where(Tag.id == tag_id, Tag.user_id == self.user_id)
                )
            )
        if favorite is not None:
            query = query.where(Note.is_favorite == favorite)
        if search is not None:
            query = query.where(search)
        if cursor:
            created, identifier = decode_cursor(cursor)
            if type(identifier) is not int:
                raise ClipoError(422, "invalid_cursor", "分页游标不匹配，请从第一页重新加载")
            query = query.where(
                or_(
                    Note.created_at < created,
                    and_(Note.created_at == created, Note.id < identifier),
                )
            )
        rows = list(
            self.db.scalars(query.order_by(Note.created_at.desc(), Note.id.desc()).limit(limit + 1))
        )
        return rows[:limit], encode_cursor(rows[limit - 1]) if len(rows) > limit else None
