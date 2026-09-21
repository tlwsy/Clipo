from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request

from app.api.dependencies import CurrentUser, Db
from app.errors import ClipoError
from app.models import CaptureJob
from app.note_repository import NoteRepository
from app.schemas.capture import (
    CaptureRequest,
    JobPage,
    JobResponse,
    NotePage,
    NoteResponse,
    NoteUpdate,
    TagRequest,
    TagResponse,
)
from app.services import notes as note_service

router = APIRouter()


def repository(db: Db, user: CurrentUser) -> NoteRepository:
    return NoteRepository(db, user.id)


Repo = Annotated[NoteRepository, Depends(repository)]
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
def notes(
    repository: Repo,
    cursor: Cursor = None,
    limit: Limit = 50,
    tag_id: Annotated[int | None, Query(ge=1)] = None,
    favorite: bool | None = None,
) -> NotePage:
    return note_service.list_notes(repository, cursor, limit, tag_id, favorite)


@router.get("/notes/{note_id}", response_model=NoteResponse, tags=["notes"])
def note(note_id: int, repository: Repo) -> NoteResponse:
    return note_service.read_note(repository, note_id)


@router.patch("/notes/{note_id}", response_model=NoteResponse, tags=["notes"])
def update_note(note_id: int, payload: NoteUpdate, repository: Repo) -> NoteResponse:
    repository.favorite(note_id, payload.is_favorite)
    return note_service.read_note(repository, note_id)


@router.get("/tags", response_model=list[TagResponse], tags=["tags"])
def tags(repository: Repo) -> list[TagResponse]:
    return [TagResponse.model_validate(tag) for tag in repository.list_tags()]


@router.post("/notes/{note_id}/tags", response_model=TagResponse, tags=["tags"])
def add_tag(note_id: int, payload: TagRequest, repository: Repo) -> TagResponse:
    return TagResponse.model_validate(repository.add_tag(note_id, payload.name))


@router.delete("/notes/{note_id}/tags/{tag_id}", status_code=204, tags=["tags"])
def remove_tag(note_id: int, tag_id: int, repository: Repo) -> None:
    repository.remove_tag(note_id, tag_id)


@router.delete("/tags/{tag_id}", status_code=204, tags=["tags"])
def delete_tag(tag_id: int, repository: Repo) -> None:
    repository.delete_tag(tag_id)


@router.delete("/notes/{note_id}", status_code=204, tags=["notes"])
def delete_note(note_id: int, repository: Repo):
    repository.delete_note(note_id)
