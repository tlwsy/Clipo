# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Remember every request merged into an active summary job."""

import sqlalchemy as sa
from alembic import op

revision = "0015_summary_request_keys"
down_revision = "0014_access_buckets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "summary_request_keys",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("request_key", sa.String(128), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(32),
            sa.ForeignKey("summary_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_summary_request_keys_job_id", "summary_request_keys", ["job_id"])
    op.execute(
        sa.text(
            "INSERT INTO summary_request_keys (user_id, request_key, job_id) "
            "SELECT user_id, request_key, id FROM summary_jobs"
        )
    )


def downgrade() -> None:
    op.drop_table("summary_request_keys")
