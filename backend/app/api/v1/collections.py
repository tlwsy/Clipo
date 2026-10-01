# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CurrentUser, Db
from app.api.v1.captures import Cursor, Limit
from app.collection_repository import CollectionRepository
from app.schemas.capture import NotePage
from app.schemas.collection import (
    CollectionCreate,
    CollectionNotes,
    CollectionPage,
    CollectionResponse,
    CollectionUpdate,
)
from app.services.notes import list_notes

router = APIRouter(prefix="/collections", tags=["collections"])


def repository(db: Db, user: CurrentUser) -> CollectionRepository:
    return CollectionRepository(db, user.id)


Repo = Annotated[CollectionRepository, Depends(repository)]


@router.get("", response_model=CollectionPage)
def collections(
    repository: Repo, note_id: Annotated[int | None, Query(gt=0)] = None
) -> CollectionPage:
    return CollectionPage(collections=repository.list_collections(note_id))


@router.post("", status_code=201, response_model=CollectionResponse)
def create(payload: CollectionCreate, repository: Repo) -> CollectionResponse:
    return repository.save(payload)


@router.patch("/{collection_id}", response_model=CollectionResponse)
def update(collection_id: int, payload: CollectionUpdate, repository: Repo) -> CollectionResponse:
    return repository.save(payload, collection_id)


@router.delete("/{collection_id}", status_code=204)
def delete(collection_id: int, repository: Repo) -> None:
    repository.delete_collection(collection_id)


@router.post("/{collection_id}/notes", status_code=204)
def add_notes(collection_id: int, payload: CollectionNotes, repository: Repo) -> None:
    repository.change_notes(collection_id, payload.note_ids)


@router.delete("/{collection_id}/notes", status_code=204)
def remove_notes(collection_id: int, payload: CollectionNotes, repository: Repo) -> None:
    repository.change_notes(collection_id, payload.note_ids, remove=True)


@router.get("/{collection_id}/notes", response_model=NotePage)
def notes(
    collection_id: int, repository: Repo, cursor: Cursor = None, limit: Limit = 50
) -> NotePage:
    repository.collection(collection_id)
    return list_notes(repository, cursor, limit, None, None, collection_id=collection_id)
