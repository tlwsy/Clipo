"""capture pipeline

Revision ID: 0002_capture
Revises: 0001_identity
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_capture"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "content",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_extraction_cache_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_cache")),
        sa.UniqueConstraint("user_id", "url_hash", name=op.f("uq_extraction_cache_user_id")),
    )
    with op.batch_alter_table("extraction_cache", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_extraction_cache_user_id"), ["user_id"], unique=False)

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("origin_url", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("author_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sources_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
    )
    with op.batch_alter_table("sources", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sources_user_id"), ["user_id"], unique=False)

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "content",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("summary_markdown", sa.Text(), nullable=True),
        sa.Column(
            "key_points",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "suggested_tags",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_notes_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
    )
    with op.batch_alter_table("notes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_notes_user_id"), ["user_id"], unique=False)

    op.create_table(
        "capture_jobs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("note_id", sa.Integer(), nullable=True),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["notes.id"],
            name=op.f("fk_capture_jobs_note_id_notes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_capture_jobs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capture_jobs")),
        sa.UniqueConstraint("user_id", "idempotency_key", name=op.f("uq_capture_jobs_user_id")),
    )
    with op.batch_alter_table("capture_jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_capture_jobs_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_capture_jobs_user_id"), ["user_id"], unique=False)

    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("likes", sa.Integer(), nullable=False),
        sa.Column("replies", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"], ["notes.id"], name=op.f("fk_comments_note_id_notes"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    with op.batch_alter_table("comments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_comments_note_id"), ["note_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("comments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_comments_note_id"))

    op.drop_table("comments")
    with op.batch_alter_table("capture_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_capture_jobs_user_id"))
        batch_op.drop_index(batch_op.f("ix_capture_jobs_status"))

    op.drop_table("capture_jobs")
    with op.batch_alter_table("notes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notes_user_id"))

    op.drop_table("notes")
    with op.batch_alter_table("sources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sources_user_id"))

    op.drop_table("sources")
    with op.batch_alter_table("extraction_cache", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_extraction_cache_user_id"))

    op.drop_table("extraction_cache")
