# SPDX-License-Identifier: AGPL-3.0-or-later
"""Add user-scoped collections without changing existing note identifiers."""

import sqlalchemy as sa
from alembic import op

revision = "0017_collections"
down_revision = "0016_comment_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(20), nullable=False),
        sa.Column("icon", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_collections_user_id", "collections", ["user_id"])
    op.create_table(
        "notes_collections",
        sa.Column(
            "note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notes_collections_collection_id", "notes_collections", ["collection_id"])


def downgrade() -> None:
    op.drop_table("notes_collections")
    op.drop_table("collections")
