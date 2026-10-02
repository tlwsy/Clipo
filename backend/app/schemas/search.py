# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Literal

from pydantic import BaseModel

from app.schemas.capture import NoteItem

SearchMode = Literal["auto", "semantic", "fulltext"]


class SearchResult(NoteItem):
    score: float
    similarity: float | None = None
    match_type: Literal["semantic", "fulltext", "both"]


class SearchResponse(BaseModel):
    results: list[SearchResult]
    mode: Literal["semantic", "fulltext"]
    semantic_status: Literal[
        "disabled", "unused", "queued", "running", "retrying", "ready", "failed"
    ]
    message: str | None = None
    retry_after: int | None = None


class EmbeddingIndexResponse(BaseModel):
    enabled: bool
    configured: bool
    backend: Literal["pgvector", "sqlite_exact"]
    model: str
    dimensions: int = 1536
    total: int
    ready: int
    pending: int
    failed: int
    backfill_running: bool
