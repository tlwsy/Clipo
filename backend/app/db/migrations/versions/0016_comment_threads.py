# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Preserve reply relationships and grounded comment insights."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_comment_threads"
down_revision = "0015_summary_request_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("comments", sa.Column("source_id", sa.String(200)))
    op.add_column("comments", sa.Column("parent_source_id", sa.String(200)))
    op.add_column(
        "notes",
        sa.Column(
            "comment_insights",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("notes", "comment_insights")
    op.drop_column("comments", "parent_source_id")
    op.drop_column("comments", "source_id")
