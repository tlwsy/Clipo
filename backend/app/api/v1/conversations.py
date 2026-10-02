# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import CurrentUser, Db
from app.conversation_repository import ConversationRepository
from app.models.conversation import ConversationJob
from app.schemas.conversation import (
    ConversationHistory,
    ConversationJobResponse,
    ConversationRequest,
)

router = APIRouter(tags=["conversations"])


def repository(db: Db, user: CurrentUser) -> ConversationRepository:
    return ConversationRepository(db, user.id)


Repo = Annotated[ConversationRepository, Depends(repository)]


@router.get("/notes/{note_id}/conversations", response_model=ConversationHistory)
def history(
    note_id: int,
    repository: Repo,
    before: int | None = Query(None, ge=0),
    limit: int = Query(20, ge=1, le=50),
) -> ConversationHistory:
    return repository.history(note_id, before, limit)


@router.post(
    "/notes/{note_id}/conversations", response_model=ConversationJobResponse, status_code=202
)
def submit(
    note_id: int, payload: ConversationRequest, repository: Repo, request: Request
) -> ConversationJob:
    repository.db.commit()
    request.app.state.note_limiter.conversation(repository.user_id)
    job = repository.submit(note_id, payload.question, payload.request_key)
    repository.db.commit()
    if job.status == "queued":
        request.app.state.capture_queue.conversations.enqueue(repository.user_id, job.id)
    return job


@router.post(
    "/conversation-jobs/{job_id}/retry", response_model=ConversationJobResponse, status_code=202
)
def retry(job_id: str, repository: Repo, request: Request) -> ConversationJob:
    repository.db.commit()
    request.app.state.note_limiter.conversation(repository.user_id)
    job = repository.retry(job_id)
    repository.db.commit()
    request.app.state.capture_queue.conversations.enqueue(repository.user_id, job.id)
    return job
