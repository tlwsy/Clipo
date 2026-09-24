# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable regeneration of existing note summaries."""

import sqlalchemy as sa
from alembic import op

revision = "0012_summary_jobs"
down_revision = "0011_backup_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "summary_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.String(32)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_key"),
    )
    for column in ("user_id", "note_id", "status"):
        op.create_index(f"ix_summary_jobs_{column}", "summary_jobs", [column])
    op.create_index(
        "uq_summary_jobs_active_note",
        "summary_jobs",
        ["user_id", "note_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running', 'retrying')"),
        postgresql_where=sa.text("status IN ('queued', 'running', 'retrying')"),
    )


def downgrade() -> None:
    op.drop_table("summary_jobs")
