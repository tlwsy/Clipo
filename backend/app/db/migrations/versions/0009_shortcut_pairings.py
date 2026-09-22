# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single-use, short-lived Shortcut device configuration."""

import sqlalchemy as sa
from alembic import op

revision = "0009_shortcut_pairings"
down_revision = "0008_stable_note_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shortcut_pairings",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("id", sa.String(32), nullable=False, unique=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("server_url", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("api_tokens.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    # Already issued device tokens remain manageable through the existing tokens API.
    op.drop_table("shortcut_pairings")
