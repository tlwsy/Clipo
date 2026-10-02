# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vectors and durable embedding work; SQLite uses JSON for local exact search."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0019_semantic_search"
down_revision = "0018_annotations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        # Install into public so test schemas and application schemas share the type.
        op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    op.add_column("notes", sa.Column("embedding", Vector(1536) if postgres else sa.JSON()))
    op.add_column("notes", sa.Column("embedding_key", sa.String(64)))
    op.add_column("notes", sa.Column("embedding_hash", sa.String(64)))
    op.add_column("notes", sa.Column("embedding_error", sa.Text()))
    if postgres:
        # Unlike IVFFlat, HNSW works before the first backfill, without training.
        op.create_index(
            "ix_notes_embedding",
            "notes",
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )
    op.create_table(
        "embedding_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("target_key", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="CASCADE")),
        sa.Column("config_key", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("input_text", sa.Text()),
        sa.Column("vector", sa.JSON()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("execution_id", sa.String(32)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("cursor", sa.Integer(), nullable=False),
        sa.Column("through_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "target_key"),
    )
    op.create_index("ix_embedding_jobs_user_id", "embedding_jobs", ["user_id"])
    op.create_index("ix_embedding_jobs_status", "embedding_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("embedding_jobs")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_notes_embedding", table_name="notes")
    for column in ("embedding", "embedding_key", "embedding_hash", "embedding_error"):
        op.drop_column("notes", column)
    # The extension can be shared with other applications; do not drop it.
