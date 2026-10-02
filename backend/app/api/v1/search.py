# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import Config, CurrentUser, Db
from app.errors import ClipoError
from app.schemas.search import EmbeddingIndexResponse, SearchMode, SearchResponse
from app.search_repository import SearchRepository
from app.services import semantic_search

router = APIRouter(tags=["search"])


def repository(db: Db, user: CurrentUser) -> SearchRepository:
    return SearchRepository(db, user.id)


Repo = Annotated[SearchRepository, Depends(repository)]
QueryText = Annotated[str, Query(min_length=1, max_length=200, pattern=r"^[^\x00-\x1f\x7f]*$")]


@router.get("/notes/search", response_model=SearchResponse)
@router.get("/notes/search/semantic", response_model=SearchResponse)
def search(
    repository: Repo,
    settings: Config,
    request: Request,
    q: QueryText,
    mode: SearchMode = "auto",
    limit: Annotated[int, Query(ge=1, le=30)] = 30,
    tag_id: Annotated[int | None, Query(ge=1)] = None,
    favorite: bool | None = None,
    collection_id: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> SearchResponse:
    q = q.strip()
    if not q or not q.strip('"“”').strip():
        raise ClipoError(422, "empty_query", "请输入搜索内容")
    repository.db.commit()
    request.app.state.note_limiter.consume([(f"search:user:{repository.user_id}", 120)])
    semantic_only = request.url.path.rstrip("/").endswith("/semantic")
    response = semantic_search.search_notes(
        repository,
        settings,
        request.app.state.search,
        q,
        "semantic" if semantic_only else mode,
        limit,
        tag_id,
        favorite,
        collection_id,
        semantic_only,
        cursor,
    )
    repository.db.commit()
    if response.semantic_status == "queued":
        request.app.state.capture_queue.embeddings.dispatch_pending(repository.user_id)
    return response


@router.get("/settings/search-index", response_model=EmbeddingIndexResponse)
def status(repository: Repo, settings: Config) -> EmbeddingIndexResponse:
    return semantic_search.index_status(repository, settings)


@router.post("/settings/search-index", response_model=EmbeddingIndexResponse, status_code=202)
def rebuild(repository: Repo, settings: Config, request: Request) -> EmbeddingIndexResponse:
    repository.db.commit()
    request.app.state.note_limiter.consume([(f"index:user:{repository.user_id}", 3)])
    current = semantic_search.index_status(repository, settings)
    if not current.enabled or not current.configured:
        raise ClipoError(422, "embedding_unconfigured", "请先开启语义搜索并配置模型密钥")
    job = repository.request_backfill()
    identifier = job.id
    repository.db.commit()
    request.app.state.capture_queue.embeddings.enqueue(repository.user_id, identifier)
    return semantic_search.index_status(repository, settings)
