# SPDX-License-Identifier: AGPL-3.0-or-later
import re

from app.config import Settings
from app.models import Note
from app.schemas.capture import TagResponse
from app.schemas.search import EmbeddingIndexResponse, SearchMode, SearchResponse, SearchResult
from app.search_repository import SearchRepository
from app.services.embeddings import load_embedding_config
from app.services.notes import site_name
from app.services.search import SearchBackend


def choose_mode(query: str, mode: SearchMode) -> str:
    if mode != "auto":
        return mode
    if (query.startswith('"') and query.endswith('"')) or (
        query.startswith("“") and query.endswith("”")
    ):
        return "fulltext"
    natural = (
        len(query) >= 12
        or len(query.split()) >= 3
        or re.search(r"如何|怎么|为什么|为何|关系|影响|建议|[?？]", query)
    )
    return "semantic" if natural else "fulltext"


def index_status(repository: SearchRepository, settings: Settings) -> EmbeddingIndexResponse:
    config = load_embedding_config(repository, settings)
    return EmbeddingIndexResponse(
        enabled=config.enabled,
        configured=bool(config.api_key),
        model=config.model,
        backend=(
            "pgvector" if repository.db.get_bind().dialect.name == "postgresql" else "sqlite_exact"
        ),
        **repository.index_status(config),
    )


def search_notes(
    repository: SearchRepository,
    settings: Settings,
    backend: SearchBackend,
    query: str,
    mode: SearchMode,
    limit: int,
    tag_id: int | None,
    favorite: bool | None,
    collection_id: int | None,
    semantic_only: bool = False,
) -> SearchResponse:
    selected = choose_mode(query, mode)
    lexical = (
        repository.fulltext(
            query, backend, 10 if selected == "semantic" else limit, tag_id, favorite, collection_id
        )
        if not semantic_only
        else []
    )
    semantic: list[tuple[Note, float]] = []
    state, message, retry = "unused", None, None
    if selected == "semantic":
        config = load_embedding_config(repository, settings)
        if not config.enabled or not config.api_key:
            state = "disabled"
            message = "语义搜索尚未启用或未配置密钥，当前显示关键词结果。"
        else:
            repository.cleanup_queries()
            job = repository.request_query(query, config)
            state = job.status
            if state == "ready":
                semantic = repository.semantic(job.vector, config, tag_id, favorite, collection_id)
                if not semantic:
                    message = "暂无可用向量，请在设置中补齐索引；当前显示关键词结果。"
            elif state == "failed":
                message = (
                    "语义搜索暂不可用，当前显示关键词结果；"
                    "请检查模型设置，或 10 分钟后重新尝试。"
                )
            else:
                message = "正在生成查询向量，先显示关键词结果。"
                retry = 2
    scores: dict[int, float] = {}
    notes: dict[int, Note] = {}
    types: dict[int, str] = {}
    similarities = {note.id: similarity for note, similarity in semantic}
    for source, rows in (("semantic", [row[0] for row in semantic]), ("fulltext", lexical)):
        for rank, note in enumerate(rows, 1):
            notes[note.id] = note
            scores[note.id] = scores.get(note.id, 0) + 1 / (60 + rank)
            types[note.id] = "both" if note.id in types else source
    identifiers = sorted(scores, key=lambda key: (-scores[key], -key))[:limit]
    tags = repository.tags_for(identifiers)
    results = []
    for identifier in identifiers:
        note = notes[identifier]
        source = repository.source(note)
        excerpt = note.summary_markdown or note.content.get("text", "")
        excerpt = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", excerpt)
        results.append(
            SearchResult(
                id=note.id,
                title=note.title,
                url=note.url,
                platform=source.platform,
                author=source.author,
                site_name=site_name(note),
                status=note.status,
                is_favorite=note.is_favorite,
                created_at=note.created_at,
                summary_excerpt=" ".join(excerpt.split())[:160],
                tags=[TagResponse.model_validate(tag) for tag in tags[note.id]],
                score=scores[identifier] * 30.5,
                similarity=similarities.get(identifier),
                match_type=types[identifier],
            )
        )
    if semantic_only and message:
        message = message.replace("当前显示关键词结果", "可改用关键词搜索").replace(
            "先显示关键词结果", "请稍候"
        )
    return SearchResponse(
        results=results, mode=selected, semantic_status=state, message=message, retry_after=retry
    )
