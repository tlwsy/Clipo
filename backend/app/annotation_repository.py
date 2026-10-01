# SPDX-License-Identifier: AGPL-3.0-or-later
from sqlalchemy import func, select

from app.db.base import utcnow
from app.errors import ClipoError
from app.extractors.base import CapturedContent
from app.models import Annotation, Note, UserSettings
from app.note_repository import NoteRepository
from app.schemas.annotation import AnnotationCreate, AnnotationResponse, AnnotationUpdate
from app.schemas.reading import (
    ReadingPreferences,
    ReadingStylePatch,
    patch_preferences,
    resolve_preferences,
)
from app.services.annotations import annotation_texts, selected_text


class AnnotationRepository(NoteRepository):
    def locked_note(self, note_id: int) -> Note:
        row = self.db.scalar(
            select(Note).where(Note.id == note_id, Note.user_id == self.user_id).with_for_update()
        )
        if row is None:
            raise ClipoError(404, "note_not_found", "笔记不存在或已删除，请返回笔记列表")
        return row

    def annotations(self, note_id: int) -> list[AnnotationResponse]:
        self.note(note_id)
        rows = self.db.scalars(
            select(Annotation)
            .join(Note)
            .where(
                Annotation.note_id == note_id,
                Annotation.user_id == self.user_id,
                Note.user_id == self.user_id,
            )
            .order_by(Annotation.block_index, Annotation.start_offset, Annotation.id)
        )
        return [AnnotationResponse.model_validate(row) for row in rows]

    def create_annotation(self, note_id: int, payload: AnnotationCreate) -> AnnotationResponse:
        note = self.locked_note(note_id)
        count = (
            self.db.scalar(
                select(func.count())
                .select_from(Annotation)
                .where(
                    Annotation.note_id == note_id,
                    Annotation.user_id == self.user_id,
                )
            )
            or 0
        )
        if count >= 1000:
            raise ClipoError(409, "annotation_limit", "每篇笔记最多保存 1000 条标注")
        content = CapturedContent.model_validate(note.content)
        try:
            quote = selected_text(annotation_texts(content.text, content.blocks), payload)
        except ValueError as exc:
            raise ClipoError(422, "invalid_annotation_range", str(exc)) from exc
        row = Annotation(
            note_id=note_id,
            user_id=self.user_id,
            **payload.model_dump(exclude={"selected_text"}),
            selected_text=quote,
        )
        self.db.add(row)
        note.updated_at = utcnow()
        self.db.flush()
        return AnnotationResponse.model_validate(row)

    def annotation(self, annotation_id: int) -> Annotation:
        row = self.db.scalar(
            select(Annotation)
            .join(Note)
            .where(
                Annotation.id == annotation_id,
                Annotation.user_id == self.user_id,
                Note.user_id == self.user_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ClipoError(404, "annotation_not_found", "标注不存在，请刷新笔记")
        return row

    def update_annotation(
        self, annotation_id: int, payload: AnnotationUpdate
    ) -> AnnotationResponse:
        row = self.annotation(annotation_id)
        values = {
            "highlight_color": row.highlight_color,
            "note_text": row.note_text,
            **payload.model_dump(exclude_unset=True),
        }
        if not values["highlight_color"] and not values["note_text"]:
            raise ClipoError(422, "empty_annotation", "请选择高亮颜色或填写批注，也可删除这条标注")
        row.highlight_color, row.note_text = values["highlight_color"], values["note_text"]
        row.updated_at = self.note(row.note_id).updated_at = utcnow()
        self.db.flush()
        return AnnotationResponse.model_validate(row)

    def delete_annotation(self, annotation_id: int) -> None:
        row = self.annotation(annotation_id)
        self.note(row.note_id).updated_at = utcnow()
        self.db.delete(row)
        self.db.flush()

    def reading_preferences(self) -> ReadingPreferences:
        return resolve_preferences(self.settings().reading_preferences)

    def save_preferences(self, payload: ReadingStylePatch) -> ReadingPreferences:
        row = self.db.scalar(
            select(UserSettings).where(UserSettings.user_id == self.user_id).with_for_update()
        )
        assert row is not None
        row.reading_preferences = patch_preferences(row.reading_preferences, payload)
        self.db.flush()
        return resolve_preferences(row.reading_preferences)

    def save_display(self, note_id: int, payload: ReadingStylePatch | None) -> ReadingStylePatch:
        note = self.locked_note(note_id)
        note.display_overrides = (
            patch_preferences(note.display_overrides, payload) if payload is not None else {}
        )
        note.updated_at = utcnow()
        self.db.flush()
        return ReadingStylePatch.model_validate(note.display_overrides)
