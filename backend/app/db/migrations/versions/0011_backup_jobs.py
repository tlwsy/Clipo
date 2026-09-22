# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable export, import and backup jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0011_backup_jobs"
down_revision = "0010_capture_payloads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.String(32)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("artifact", sa.String(80)),
        sa.Column("note_count", sa.Integer()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_key"),
    )
    op.create_index("ix_backup_jobs_user_id", "backup_jobs", ["user_id"])
    op.create_index("ix_backup_jobs_status", "backup_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("backup_jobs")
