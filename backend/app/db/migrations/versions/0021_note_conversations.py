# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private note conversations and durable answer jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0021_note_conversations"
down_revision = "0020_memory_gallery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_conversations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("note_id", "turn_index", "role"),
        sa.CheckConstraint("turn_index >= 0", name="turn_index"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="role"),
    )
    op.create_index("ix_note_conversations_user_id", "note_conversations", ["user_id"])
    op.create_index(
        "ix_note_conversations_note_turn", "note_conversations", ["note_id", "turn_index"]
    )
    op.create_table(
        "conversation_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.UniqueConstraint("note_id", "turn_index"),
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
        op.create_index(f"ix_conversation_jobs_{column}", "conversation_jobs", [column])
    op.create_index(
        "uq_conversation_jobs_active_note",
        "conversation_jobs",
        ["user_id", "note_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running', 'retrying')"),
        postgresql_where=sa.text("status IN ('queued', 'running', 'retrying')"),
    )


def downgrade() -> None:
    op.drop_table("conversation_jobs")
    op.drop_table("note_conversations")
