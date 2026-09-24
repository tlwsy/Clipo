# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Revocable capabilities for public note reading."""

import sqlalchemy as sa
from alembic import op

revision = "0013_shared_links"
down_revision = "0012_summary_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shared_links",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "note_id"):
        op.create_index(f"ix_shared_links_{column}", "shared_links", [column])


def downgrade() -> None:
    op.drop_table("shared_links")
