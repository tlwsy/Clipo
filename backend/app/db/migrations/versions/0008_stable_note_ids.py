# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Never reuse SQLite note IDs: offline retries and old links must remain safe."""

from alembic import op

revision = "0008_stable_note_ids"
down_revision = "0007_note_search"
branch_labels = None
depends_on = None


def rebuild(autoincrement: bool) -> None:
    if op.get_context().dialect.name != "sqlite":
        return
    # Foreign keys remain enabled. Preserve dependents across SQLite's table replacement,
    # including completed-job references affected by ON DELETE SET NULL.
    for table in ("comments", "notes_tags"):
        op.execute(f"CREATE TEMP TABLE restore_{table} AS SELECT * FROM {table}")
    op.execute("CREATE TEMP TABLE restore_jobs AS SELECT id, note_id FROM capture_jobs")
    for suffix in ("insert", "delete", "update"):
        op.execute(f"DROP TRIGGER notes_search_{suffix}")
    with op.batch_alter_table(
        "notes", recreate="always", table_kwargs={"sqlite_autoincrement": autoincrement}
    ):
        pass
    for table in ("comments", "notes_tags"):
        op.execute(f"INSERT INTO {table} SELECT * FROM restore_{table}")
        op.execute(f"DROP TABLE restore_{table}")
    op.execute("""UPDATE capture_jobs SET note_id=(
        SELECT note_id FROM restore_jobs WHERE restore_jobs.id=capture_jobs.id)""")
    op.execute("DROP TABLE restore_jobs")
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


def upgrade() -> None:
    rebuild(True)


def downgrade() -> None:
    rebuild(False)
