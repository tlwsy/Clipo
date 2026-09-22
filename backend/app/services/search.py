# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from dataclasses import dataclass

from sqlalchemy import Engine, and_, bindparam, column, func, literal_column, or_, select, text
from sqlalchemy.sql.elements import ColumnElement

from app.models import Note

PG_DOCUMENT = (
    "coalesce(title, '') || E'\\n' || coalesce(content->>'text', '') "
    "|| E'\\n' || coalesce(summary_markdown, '')"
)


@dataclass(frozen=True)
class SearchBackend:
    mode: str

    @classmethod
    def detect(cls, engine: Engine) -> "SearchBackend":
        if engine.dialect.name == "sqlite":
            return cls("sqlite_fts5")
        with engine.connect() as connection:
            bigm = connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_bigm')")
            )
        return cls("postgresql_bigm" if bigm else "postgresql_tsvector_like")

    def condition(self, query: str) -> ColumnElement[bool] | None:
        words = list(dict.fromkeys(query.split()))
        if not words:
            return None
        if self.mode == "sqlite_fts5":
            clauses = []
            for index, word in enumerate(words):
                if len(word) >= 3:
                    match = '"' + word.replace('"', '""') + '"'
                    ids = (
                        select(column("rowid"))
                        .select_from(text("notes_search"))
                        .where(
                            text(f"notes_search MATCH :search_{index}").bindparams(
                                **{f"search_{index}": match}
                            )
                        )
                    )
                    clauses.append(Note.id.in_(ids))
                else:
                    # Trigrams cannot represent one/two-character Chinese terms.
                    clauses.append(
                        or_(
                            Note.title.contains(word, autoescape=True),
                            Note.content["text"].as_string().contains(word, autoescape=True),
                            Note.summary_markdown.contains(word, autoescape=True),
                        )
                    )
            return and_(*clauses)
        document = literal_column(f"({PG_DOCUMENT})")
        vector = func.to_tsvector(literal_column("'simple'"), document)
        return and_(
            *(
                or_(
                    func.lower(document).contains(word.lower(), autoescape=True),
                    vector.op("@@")(
                        func.plainto_tsquery(
                            literal_column("'simple'"), bindparam(f"search_{index}", word)
                        )
                    ),
                )
                for index, word in enumerate(words)
            )
        )
