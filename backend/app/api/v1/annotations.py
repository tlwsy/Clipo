# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated

from fastapi import APIRouter, Depends

from app.annotation_repository import AnnotationRepository
from app.api.dependencies import CurrentUser, Db
from app.schemas.annotation import (
    AnnotationCreate,
    AnnotationPage,
    AnnotationResponse,
    AnnotationUpdate,
)
from app.schemas.reading import ReadingPreferences, ReadingStylePatch

router = APIRouter(tags=["annotations"])


def repository(db: Db, user: CurrentUser) -> AnnotationRepository:
    return AnnotationRepository(db, user.id)


Repo = Annotated[AnnotationRepository, Depends(repository)]


@router.get("/notes/{note_id}/annotations", response_model=AnnotationPage)
def annotations(note_id: int, repository: Repo) -> AnnotationPage:
    return AnnotationPage(annotations=repository.annotations(note_id))


@router.post("/notes/{note_id}/annotations", response_model=AnnotationResponse, status_code=201)
def create(note_id: int, payload: AnnotationCreate, repository: Repo) -> AnnotationResponse:
    return repository.create_annotation(note_id, payload)


@router.patch("/annotations/{annotation_id}", response_model=AnnotationResponse)
def update(annotation_id: int, payload: AnnotationUpdate, repository: Repo) -> AnnotationResponse:
    return repository.update_annotation(annotation_id, payload)


@router.delete("/annotations/{annotation_id}", status_code=204)
def delete(annotation_id: int, repository: Repo) -> None:
    repository.delete_annotation(annotation_id)


@router.get("/user/reading-preferences", response_model=ReadingPreferences)
def preferences(repository: Repo) -> ReadingPreferences:
    return repository.reading_preferences()


@router.patch("/user/reading-preferences", response_model=ReadingPreferences)
def save_preferences(payload: ReadingStylePatch, repository: Repo) -> ReadingPreferences:
    return repository.save_preferences(payload)


@router.patch(
    "/notes/{note_id}/display", response_model=ReadingStylePatch, response_model_exclude_none=True
)
def save_display(note_id: int, payload: ReadingStylePatch, repository: Repo) -> ReadingStylePatch:
    return repository.save_display(note_id, payload)


@router.delete("/notes/{note_id}/display", status_code=204)
def reset_display(note_id: int, repository: Repo) -> None:
    repository.save_display(note_id, None)
