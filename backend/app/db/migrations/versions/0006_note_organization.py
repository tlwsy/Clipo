# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tags, favorites and backfill of existing model suggestions."""

import sqlalchemy as sa
from alembic import op

revision = "0006_note_organization"
down_revision = "0005_platform_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notes", sa.Column("is_favorite", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    tags = op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(50), nullable=False),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_tags_user_id", "tags", ["user_id"])
    links = op.create_table(
        "notes_tags",
        sa.Column(
            "note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
        ),
    )
    # SQL-only backfill works for online migrations and generated PostgreSQL DDL.
    if op.get_context().dialect.name == "postgresql":
        op.execute("""INSERT INTO tags (user_id, name)
            SELECT DISTINCT user_id, left(trim(regexp_replace(value, '\\s+', ' ', 'g')), 50)
            FROM notes, jsonb_array_elements_text(suggested_tags) AS value
            WHERE trim(value) <> '' ON CONFLICT DO NOTHING""")
        op.execute("""INSERT INTO notes_tags (note_id, tag_id)
            SELECT DISTINCT n.id, t.id FROM notes n,
            jsonb_array_elements_text(n.suggested_tags) AS value, tags t
            WHERE t.user_id = n.user_id
            AND t.name = left(trim(regexp_replace(value, '\\s+', ' ', 'g')), 50)
            ON CONFLICT DO NOTHING""")
    else:
        # Python normalization also collapses Unicode whitespace on SQLite.
        import json

        connection = op.get_bind()
        for note_id, user_id, raw in connection.execute(
            sa.text("SELECT id, user_id, suggested_tags FROM notes")
        ):
            for name in dict.fromkeys(" ".join(name.split())[:50] for name in json.loads(raw)):
                if not name:
                    continue
                connection.execute(
                    sa.text("INSERT OR IGNORE INTO tags (user_id, name) VALUES (:u, :n)"),
                    {"u": user_id, "n": name},
                )
                tag_id = connection.scalar(
                    sa.select(tags.c.id).where(tags.c.user_id == user_id, tags.c.name == name)
                )
                connection.execute(links.insert().values(note_id=note_id, tag_id=tag_id))


def downgrade() -> None:
    op.drop_table("notes_tags")
    op.drop_table("tags")
    op.drop_column("notes", "is_favorite")
