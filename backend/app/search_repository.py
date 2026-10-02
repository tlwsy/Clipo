# SPDX-License-Identifier: AGPL-3.0-or-later
import heapq
import math
from collections.abc import Iterator

from sqlalchemy import case, or_, text

from app.embedding_repository import EmbeddingRepository
from app.models import Note
from app.services.embeddings import EmbeddingConfig
from app.services.search import SearchBackend


class SearchRepository(EmbeddingRepository):
    def fulltext(
        self,
        query: str,
        backend: SearchBackend,
        limit: int,
        tag_id: int | None,
        favorite: bool | None,
        collection_id: int | None,
    ) -> list[Note]:
        # Quotes opt into an exact phrase, matching the existing literal search semantics.
        phrase = query.startswith(('"', "“")) and query.endswith(('"', "”"))
        query = query.strip('"“”')
        condition = (
            or_(
                Note.title.contains(query, autoescape=True),
                Note.summary_markdown.contains(query, autoescape=True),
                Note.content["text"].as_string().contains(query, autoescape=True),
            )
            if phrase
            else backend.condition(query)
        )
        if condition is None:
            return []
        return list(
            self.db.scalars(
                self.filtered_notes(tag_id, favorite, collection_id)
                .where(condition)
                .order_by(
                    case(
                        (Note.title == query, 3),
                        (Note.title.contains(query, autoescape=True), 2),
                        (Note.summary_markdown.contains(query, autoescape=True), 1),
                        else_=0,
                    ).desc(),
                    Note.created_at.desc(),
                    Note.id.desc(),
                )
                .limit(limit)
            )
        )

    def semantic(
        self,
        vector: list[float],
        config: EmbeddingConfig,
        tag_id: int | None,
        favorite: bool | None,
        collection_id: int | None,
        limit: int = 20,
    ) -> list[tuple[Note, float]]:
        query = self.filtered_notes(tag_id, favorite, collection_id).where(
            Note.embedding_key == config.key,
            Note.embedding.is_not(None),
        )
        if self.db.get_bind().dialect.name == "postgresql":
            # Iterative scans avoid losing matches after tenant/tag/space filtering.
            self.db.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
            distance = Note.embedding.cosine_distance(vector)
            rows = list(
                self.db.execute(query.add_columns(distance).order_by(distance).limit(limit))
            )
            if len(rows) < limit:
                # Exact fallback for selective filters or exhausted approximate scan budgets.
                rows = list(
                    self.db.execute(
                        query.add_columns(distance)
                        .order_by(distance + 0, Note.id.desc())
                        .limit(limit)
                    )
                )
            return [(note, max(-1.0, min(1.0, 1 - float(value)))) for note, value in rows]

        # SQLite is a development/small-library fallback. Stream vectors and retain only top K.
        def candidates() -> Iterator[tuple[float, int, Note]]:
            for note, stored in self.db.execute(
                query.add_columns(Note.embedding).execution_options(yield_per=100)
            ):
                norm = math.hypot(*stored) * math.hypot(*vector)
                similarity = sum(a * b for a, b in zip(stored, vector, strict=True)) / norm
                yield similarity, note.id, note

        return [
            (note, max(-1.0, min(1.0, similarity)))
            for similarity, _, note in heapq.nlargest(limit, candidates(), key=lambda row: row[:2])
        ]
