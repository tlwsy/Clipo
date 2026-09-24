# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import CurrentUser, Db
from app.models import SummaryJob
from app.schemas.summary import SummaryJobResponse, SummaryRequest
from app.summary_repository import SummaryRepository

router = APIRouter(tags=["notes"])


def repository(db: Db, user: CurrentUser) -> SummaryRepository:
    return SummaryRepository(db, user.id)


Repo = Annotated[SummaryRepository, Depends(repository)]


@router.post("/notes/{note_id}/summarize", response_model=SummaryJobResponse, status_code=202)
def submit(note_id: int, payload: SummaryRequest, repository: Repo, request: Request) -> SummaryJob:
    # Authentication may flush API-token last_used_at; release its SQLite write lock first.
    repository.db.commit()
    request.app.state.note_limiter.summary(repository.user_id)
    job = repository.submit_summary(note_id, payload.request_key)
    repository.db.commit()
    if job.status == "queued":
        request.app.state.capture_queue.summaries.enqueue(repository.user_id, job.id)
    return job


@router.get("/notes/{note_id}/summary-job", response_model=SummaryJobResponse | None)
def latest(note_id: int, repository: Repo) -> SummaryJob | None:
    return repository.latest_summary(note_id)


@router.get("/summary-jobs/{job_id}", response_model=SummaryJobResponse)
def read(job_id: str, repository: Repo) -> SummaryJob:
    return repository.summary_job(job_id)


@router.post("/summary-jobs/{job_id}/retry", response_model=SummaryJobResponse, status_code=202)
def retry(job_id: str, repository: Repo, request: Request) -> SummaryJob:
    repository.db.commit()
    request.app.state.note_limiter.summary(repository.user_id)
    job = repository.retry_summary(job_id)
    repository.db.commit()
    request.app.state.capture_queue.summaries.enqueue(repository.user_id, job.id)
    return job
