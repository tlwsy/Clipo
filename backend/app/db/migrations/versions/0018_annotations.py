# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private annotations and scoped reading preferences."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_annotations"
down_revision = "0017_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, column in (("notes", "display_overrides"), ("user_settings", "reading_preferences")):
        op.add_column(
            table,
            sa.Column(
                column,
                sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
                nullable=False,
                server_default="{}",
            ),
        )
    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("selected_text", sa.Text(), nullable=False),
        sa.Column("highlight_color", sa.String(20)),
        sa.Column("note_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("block_index >= 0", name="annotation_block_index"),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="annotation_range"
        ),
    )
    op.create_index("ix_annotations_note_id", "annotations", ["note_id"])
    op.create_index("ix_annotations_user_id", "annotations", ["user_id"])


def downgrade() -> None:
    op.drop_table("annotations")
    op.drop_column("notes", "display_overrides")
    op.drop_column("user_settings", "reading_preferences")
