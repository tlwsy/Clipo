# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.api.v1.captures import Repo
from app.schemas.note_export import ExportOptions
from app.services.note_export import EXPORT_CSP, ExportService, export_filename

router = APIRouter(tags=["exports"])
Options = Annotated[ExportOptions, Query()]


class MarkdownResponse(PlainTextResponse):
    media_type = "text/markdown"


def headers(service: ExportService, extension: str) -> dict[str, str]:
    note = service.note
    filename = quote(export_filename(note.title, note.id, extension), safe="")
    return {
        "Content-Disposition": (
            f'attachment; filename="note-{note.id}.{extension}"; ' f"filename*=UTF-8''{filename}"
        ),
        "Cache-Control": "no-store, private",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": EXPORT_CSP,
    }


@router.get(
    "/notes/{note_id}/export/markdown",
    response_class=Response,
    responses={200: {"content": {"text/markdown": {"schema": {"type": "string"}}}}},
)
def export_markdown(note_id: int, repository: Repo, options: Options) -> MarkdownResponse:
    service = ExportService(repository, note_id, options)
    return MarkdownResponse(service.export_markdown(), headers=headers(service, "md"))


@router.get(
    "/notes/{note_id}/export/html",
    response_class=Response,
    responses={200: {"content": {"text/html": {"schema": {"type": "string"}}}}},
)
def export_html(note_id: int, repository: Repo, options: Options) -> HTMLResponse:
    service = ExportService(repository, note_id, options)
    return HTMLResponse(service.export_html(), headers=headers(service, "html"))
