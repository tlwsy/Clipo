# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CurrentUser, Db
from app.memory_repository import MemoryGalleryRepository
from app.schemas.memory import MemoryDismiss, MemoryGallery, NoteView

router = APIRouter(tags=["memory"])


def repository(db: Db, user: CurrentUser) -> MemoryGalleryRepository:
    return MemoryGalleryRepository(db, user.id)


Repo = Annotated[MemoryGalleryRepository, Depends(repository)]


@router.get("/memory-gallery", response_model=MemoryGallery)
def gallery(repository: Repo, count: int = Query(default=15, ge=10, le=15)) -> MemoryGallery:
    return repository.gallery(count)


@router.post("/notes/{note_id}/view", status_code=204)
def view(note_id: int, payload: NoteView, repository: Repo) -> None:
    repository.record_view(note_id, payload.duration_seconds)


@router.post("/memory-gallery/dismiss", status_code=204)
def dismiss(payload: MemoryDismiss, repository: Repo) -> None:
    repository.dismiss(payload.note_id)
