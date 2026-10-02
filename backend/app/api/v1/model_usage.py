# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import CurrentUser, Db
from app.model_usage_repository import ModelUsageRepository
from app.schemas.model_usage import ModelUsageResponse, ModelUsageUpdate

router = APIRouter(prefix="/settings/model-usage", tags=["settings"])


def repository(db: Db, user: CurrentUser) -> ModelUsageRepository:
    return ModelUsageRepository(db, user.id)


Repo = Annotated[ModelUsageRepository, Depends(repository)]


@router.get("", response_model=ModelUsageResponse)
def status(repository: Repo) -> ModelUsageResponse:
    return repository.status()


@router.put("", response_model=ModelUsageResponse)
def configure(payload: ModelUsageUpdate, repository: Repo) -> ModelUsageResponse:
    repository.set_limit(payload.monthly_limit)
    return repository.status()
