# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Maintain searchable note text on both database backends."""

from alembic import op

revision = "0007_note_search"
down_revision = "0006_note_organization"
branch_labels = None
depends_on = None

# Keep this expression identical to the search query, so PostgreSQL can use its indexes.
DOCUMENT = (
    "coalesce(title, '') || E'\\n' || coalesce(content->>'text', '') "
    "|| E'\\n' || coalesce(summary_markdown, '')"
)


def upgrade() -> None:
    if op.get_context().dialect.name == "sqlite":
        op.execute(
            "CREATE VIRTUAL TABLE notes_search USING fts5(title, body, summary, tokenize='trigram')"
        )
        op.execute("""INSERT INTO notes_search(rowid, title, body, summary)
            SELECT id, title, json_extract(content, '$.text'), coalesce(summary_markdown, '')
            FROM notes""")
        op.execute("""CREATE TRIGGER notes_search_insert AFTER INSERT ON notes BEGIN
            INSERT INTO notes_search(rowid, title, body, summary)
            VALUES (new.id, new.title, json_extract(new.content, '$.text'),
                coalesce(new.summary_markdown, ''));
            END""")
        op.execute("""CREATE TRIGGER notes_search_delete AFTER DELETE ON notes BEGIN
            DELETE FROM notes_search WHERE rowid=old.id;
            END""")
        op.execute("""CREATE TRIGGER notes_search_update
            AFTER UPDATE OF title, content, summary_markdown ON notes BEGIN
            DELETE FROM notes_search WHERE rowid=old.id;
            INSERT INTO notes_search(rowid, title, body, summary)
            VALUES (new.id, new.title, json_extract(new.content, '$.text'),
                coalesce(new.summary_markdown, ''));
            END""")
    else:
        op.execute(
            f"CREATE INDEX ix_notes_search ON notes USING gin(to_tsvector('simple', {DOCUMENT}))"
        )
        # Do not require privileges to install extensions. Use bigram indexing when preinstalled.
        op.execute(f"""DO $migration$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_bigm') THEN
                CREATE INDEX ix_notes_search_bigm ON notes
                USING gin (lower({DOCUMENT}) gin_bigm_ops);
            END IF;
            END $migration$""")


def downgrade() -> None:
    if op.get_context().dialect.name == "sqlite":
        for name in ("insert", "delete", "update"):
            op.execute(f"DROP TRIGGER notes_search_{name}")
        op.execute("DROP TABLE notes_search")
    else:
        op.execute("DROP INDEX IF EXISTS ix_notes_search_bigm")
        op.execute("DROP INDEX ix_notes_search")
