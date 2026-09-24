# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import CurrentUser, Db
from app.schemas.sharing import (
    IssuedShareResponse,
    PublicNoteResponse,
    PublicReadRequest,
    ShareRequest,
    ShareResponse,
)
from app.services.sharing import read_public_note
from app.sharing_repository import SharingRepository, resolve_share

router = APIRouter(tags=["sharing"])


def repository(db: Db, user: CurrentUser) -> SharingRepository:
    return SharingRepository(db, user.id)


Repo = Annotated[SharingRepository, Depends(repository)]


@router.get("/notes/{note_id}/shares", response_model=list[ShareResponse])
def list_links(note_id: int, repository: Repo) -> list[ShareResponse]:
    return [ShareResponse.model_validate(row) for row in repository.list_shares(note_id)]


@router.post("/notes/{note_id}/shares", response_model=IssuedShareResponse, status_code=201)
def create(
    note_id: int, payload: ShareRequest, repository: Repo, request: Request
) -> IssuedShareResponse:
    # Commit only authentication bookkeeping before the limiter's separate transaction.
    repository.db.commit()
    request.app.state.note_limiter.share(repository.user_id)
    link, token = repository.create_share(note_id, payload.expires_in_days)
    return IssuedShareResponse(**ShareResponse.model_validate(link).model_dump(), token=token)


@router.delete("/notes/{note_id}/shares/{share_id}", status_code=204)
def revoke(note_id: int, share_id: str, repository: Repo) -> None:
    repository.revoke_share(note_id, share_id)


@router.post("/public/notes/read", response_model=PublicNoteResponse)
def read(payload: PublicReadRequest, db: Db) -> PublicNoteResponse:
    repository, note_id = resolve_share(db, payload.token.get_secret_value())
    return read_public_note(repository, note_id)
