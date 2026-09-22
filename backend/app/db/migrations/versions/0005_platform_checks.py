# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable per-user, per-credential platform login checks."""

import sqlalchemy as sa
from alembic import op

revision = "0005_platform_checks"
down_revision = "0004_capture_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_checks",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("platform", sa.String(32), primary_key=True),
        sa.Column("request_id", sa.String(32), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("execution_id", sa.String(32)),
    )


def downgrade() -> None:
    op.drop_table("platform_checks")
