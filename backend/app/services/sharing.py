# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from app.extractors.base import CapturedContent
from app.schemas.sharing import PublicComment, PublicNoteResponse
from app.security.urls import UnsafeURL, normalize_url
from app.sharing_repository import SharingRepository


def public_url(value: str) -> str | None:
    try:
        return normalize_url(value)
    except UnsafeURL:
        return None


def read_public_note(repository: SharingRepository, note_id: int) -> PublicNoteResponse:
    note = repository.note(note_id)
    source = repository.source(note)
    content = CapturedContent.model_validate(note.content)
    return PublicNoteResponse(
        title=note.title,
        url=public_url(note.url),
        platform=source.platform,
        author=source.author,
        published_at=source.published_at,
        text=content.text,
        images=[safe for url in content.images if (safe := public_url(url)) is not None],
        blocks=content.blocks,
        summary_markdown=note.summary_markdown,
        key_points=note.key_points,
        comment_insights=note.comment_insights,
        comments=[
            PublicComment.model_validate(comment) for comment in repository.comments(note.id)
        ],
    )
