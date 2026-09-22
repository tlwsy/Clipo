# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Browser payloads and durable, bounded chunk uploads."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_capture_payloads"
down_revision = "0009_shortcut_pairings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "capture_jobs",
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True
        ),
    )
    op.add_column("capture_jobs", sa.Column("request_hash", sa.String(64), nullable=True))
    op.create_table(
        "capture_uploads",
        sa.Column(
            "job_id",
            sa.String(40),
            sa.ForeignKey("capture_jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_capture_uploads_user_id", "capture_uploads", ["user_id"])
    op.create_table(
        "capture_upload_chunks",
        sa.Column(
            "job_id",
            sa.String(40),
            sa.ForeignKey("capture_uploads.job_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("capture_upload_chunks")
    op.drop_table("capture_uploads")
    # SQLite supports DROP COLUMN; no table rebuild that could cascade note references.
    op.drop_column("capture_jobs", "request_hash")
    op.drop_column("capture_jobs", "payload")
