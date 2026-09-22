# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Add per-user capture settings, retaining the existing comment limit by default."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_capture_settings"
down_revision = "0003_comment_scoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "capture_config",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    # Native DROP COLUMN avoids rebuilding a table referenced by account data on SQLite.
    op.drop_column("user_settings", "capture_config")
