# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared bounded-window counters for note actions and anonymous reads."""

import sqlalchemy as sa
from alembic import op

revision = "0014_access_buckets"
down_revision = "0013_shared_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_buckets",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_access_buckets_expires_at", "access_buckets", ["expires_at"])


def downgrade() -> None:
    op.drop_table("access_buckets")
