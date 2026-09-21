import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request

from app.api.dependencies import CurrentUser, Db
from app.capture_repository import CaptureRepository
from app.errors import ClipoError
from app.models import CaptureJob, Note
from app.schemas.capture import (
    CaptureRequest,
    CommentResponse,
    JobPage,
    JobResponse,
    NoteItem,
    NotePage,
    NoteResponse,
    SourceResponse,
)

router = APIRouter()


def repository(db: Db, user: CurrentUser) -> CaptureRepository:
    return CaptureRepository(db, user.id)


Repo = Annotated[CaptureRepository, Depends(repository)]
Cursor = Annotated[str | None, Query(max_length=512)]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.post("/captures", status_code=202, response_model=JobResponse, tags=["captures"])
def capture(
    payload: CaptureRequest,
    repository: Repo,
    request: Request,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
):
    job = repository.create_job(payload.url, idempotency_key)
    repository.db.commit()
    if job.status == "queued":
        request.app.state.capture_queue.enqueue(repository.user_id, job.id)
    return job


@router.get("/jobs", response_model=JobPage, tags=["captures"])
def jobs(
    repository: Repo,
    cursor: Cursor = None,
    limit: Limit = 50,
    status: Annotated[str | None, Query(max_length=100)] = None,
):
    statuses = status.split(",") if status else None
    if statuses and not set(statuses) <= {"queued", "running", "retrying", "failed", "success"}:
        raise ClipoError(422, "invalid_status", "任务状态无效，请重新选择筛选条件")
    rows, next_cursor = repository.page(CaptureJob, cursor, limit, statuses)
    return JobPage(items=[JobResponse.model_validate(row) for row in rows], next_cursor=next_cursor)


@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["captures"])
def job(job_id: str, repository: Repo):
    return repository.job(job_id)


@router.post("/jobs/{job_id}/retry", status_code=202, response_model=JobResponse, tags=["captures"])
def retry(job_id: str, repository: Repo, request: Request):
    job = repository.retry(job_id)
    repository.db.commit()
    request.app.state.capture_queue.enqueue(repository.user_id, job.id)
    return job


@router.get("/notes", response_model=NotePage, tags=["notes"])
def notes(repository: Repo, cursor: Cursor = None, limit: Limit = 50):
    rows, next_cursor = repository.page(Note, cursor, limit)
    items = []
    for note in rows:
        source = repository.source(note)
        excerpt = note.summary_markdown or note.content["text"]
        if note.summary_markdown:
            excerpt = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", excerpt)
            excerpt = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s+|[-*+]\s+|>\s*)", "", excerpt)
            excerpt = excerpt.replace("**", "").replace("__", "").replace("`", "")
        excerpt = " ".join(excerpt.split())[:160]
        items.append(
            NoteItem(
                id=note.id,
                title=note.title,
                url=note.url,
                platform=source.platform,
                author=source.author,
                summary_excerpt=excerpt,
                status=note.status,
                created_at=note.created_at,
            )
        )
    return NotePage(items=items, next_cursor=next_cursor)


@router.get("/notes/{note_id}", response_model=NoteResponse, tags=["notes"])
def note(note_id: int, repository: Repo) -> NoteResponse:
    note = repository.note(note_id)
    content = dict(note.content)
    # The snapshot is retained in storage but never rendered or sent to the reader.
    content["raw_html"] = None
    return NoteResponse(
        id=note.id,
        title=note.title,
        url=note.url,
        source=SourceResponse.model_validate(repository.source(note)),
        content=content,
        comments=[
            CommentResponse.model_validate(comment) for comment in repository.comments(note.id)
        ],
        summary_markdown=note.summary_markdown,
        key_points=note.key_points,
        suggested_tags=note.suggested_tags,
        status=note.status,
        summary_error=note.summary_error,
        comment_score_error=note.comment_score_error,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.delete("/notes/{note_id}", status_code=204, tags=["notes"])
def delete_note(note_id: int, repository: Repo):
    repository.delete_note(note_id)
