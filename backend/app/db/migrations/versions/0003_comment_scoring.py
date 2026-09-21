"""Add optional comment scores while preserving existing notes and comments.

Revision ID: 0003_comment_scoring
Revises: 0002_capture
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_comment_scoring"
down_revision = "0002_capture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notes", sa.Column("comment_score_error", sa.Text(), nullable=True))
    op.add_column("comments", sa.Column("ai_score", sa.Float(), nullable=True))
    op.add_column("comments", sa.Column("ai_reason", sa.Text(), nullable=True))
    op.add_column(
        "comments",
        sa.Column("is_valuable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    # Native DROP COLUMN avoids rebuilding SQLite parent tables with cascading foreign keys.
    op.drop_column("comments", "is_valuable")
    op.drop_column("comments", "ai_reason")
    op.drop_column("comments", "ai_score")
    op.drop_column("notes", "comment_score_error")
