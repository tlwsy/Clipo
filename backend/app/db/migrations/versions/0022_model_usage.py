# SPDX-License-Identifier: AGPL-3.0-or-later
"""Account monthly model request limits and durable usage counters."""

import sqlalchemy as sa
from alembic import op

revision = "0022_model_usage"
down_revision = "0021_note_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("monthly_model_limit", sa.Integer()))
    op.create_table(
        "model_usage",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("calls", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("calls >= 0", name="calls"),
    )


def downgrade() -> None:
    op.drop_table("model_usage")
    op.drop_column("user_settings", "monthly_model_limit")
