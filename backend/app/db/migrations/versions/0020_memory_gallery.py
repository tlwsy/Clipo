# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private reading history and expiring memory dismissals."""

import sqlalchemy as sa
from alembic import op

revision = "0020_memory_gallery"
down_revision = "0019_semantic_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notes", sa.Column("last_viewed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "notes",
        sa.Column("reading_duration_seconds", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_notes_last_viewed_at", "notes", ["last_viewed_at"])
    op.create_table(
        "memory_gallery_dismissals",
        sa.Column(
            "note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_memory_gallery_dismissals_dismissed_at", "memory_gallery_dismissals", ["dismissed_at"]
    )


def downgrade() -> None:
    op.drop_table("memory_gallery_dismissals")
    op.drop_index("ix_notes_last_viewed_at", table_name="notes")
    op.drop_column("notes", "reading_duration_seconds")
    op.drop_column("notes", "last_viewed_at")
