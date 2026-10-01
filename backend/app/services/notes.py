# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import re

from sqlalchemy.sql.elements import ColumnElement

from app.annotation_repository import AnnotationRepository
from app.extractors.site_name import clean_site_name, site_name_from_html
from app.models import Note
from app.note_repository import NoteRepository
from app.schemas.capture import (
    CommentResponse,
    NoteItem,
    NotePage,
    NoteResponse,
    SourceResponse,
    TagResponse,
)


def site_name(note: Note) -> str | None:
    return clean_site_name(note.content.get("site_name")) or site_name_from_html(
        note.content.get("raw_html")
    )


def read_note(repository: NoteRepository, note_id: int) -> NoteResponse:
    note = repository.note(note_id)
    content = dict(note.content)
    content["raw_html"] = None
    content["site_name"] = site_name(note)
    source = SourceResponse.model_validate(repository.source(note))
    source.site_name = content["site_name"]
    return NoteResponse(
        id=note.id,
        title=note.title,
        url=note.url,
        source=source,
        content=content,
        annotations=AnnotationRepository(repository.db, repository.user_id).annotations(note.id),
        reading_preferences=AnnotationRepository(
            repository.db, repository.user_id
        ).reading_preferences(),
        display_overrides=note.display_overrides,
        comments=[CommentResponse.model_validate(row) for row in repository.comments(note.id)],
        summary_markdown=note.summary_markdown,
        key_points=note.key_points,
        suggested_tags=note.suggested_tags,
        status=note.status,
        summary_error=note.summary_error,
        comment_score_error=note.comment_score_error,
        comment_insights=note.comment_insights,
        created_at=note.created_at,
        updated_at=note.updated_at,
        is_favorite=note.is_favorite,
        tags=[TagResponse.model_validate(tag) for tag in repository.tags_for([note.id])[note.id]],
    )


def list_notes(
    repository: NoteRepository,
    cursor: str | None,
    limit: int,
    tag_id: int | None,
    favorite: bool | None,
    search: ColumnElement[bool] | None = None,
    collection_id: int | None = None,
) -> NotePage:
    rows, next_cursor = repository.list_notes(
        cursor, limit, tag_id, favorite, search, collection_id
    )
    tags = repository.tags_for([note.id for note in rows])
    items = []
    for note in rows:
        source = repository.source(note)
        excerpt = note.summary_markdown or note.content["text"]
        if note.summary_markdown:
            excerpt = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", excerpt)
            excerpt = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s+|[-*+]\s+|>\s*)", "", excerpt)
            excerpt = excerpt.replace("**", "").replace("__", "").replace("`", "")
        items.append(
            NoteItem(
                id=note.id,
                title=note.title,
                url=note.url,
                platform=source.platform,
                site_name=site_name(note),
                author=source.author,
                summary_excerpt=" ".join(excerpt.split())[:160],
                status=note.status,
                created_at=note.created_at,
                is_favorite=note.is_favorite,
                tags=[TagResponse.model_validate(tag) for tag in tags[note.id]],
            )
        )
    return NotePage(items=items, next_cursor=next_cursor)
