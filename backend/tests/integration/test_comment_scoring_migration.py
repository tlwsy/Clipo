from io import StringIO

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT, Settings
from app.db.base import utcnow
from app.extractors.base import CapturedContent
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_existing_notes_comments_and_jobs_survive_scoring_upgrade_and_rollback(
    app: FastAPI,
    client: TestClient,
    auth: dict[str, str],
) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    now = utcnow()
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0002_capture")
        metadata = sa.MetaData()
        metadata.reflect(bind=connection)
        connection.execute(
            metadata.tables["sources"]
            .insert()
            .values(
                id=1,
                user_id=1,
                platform="web",
                origin_url="https://example.com",
            )
        )
        connection.execute(
            metadata.tables["notes"]
            .insert()
            .values(
                id=1,
                user_id=1,
                source_id=1,
                title="升级前的笔记",
                url="https://example.com",
                content=CapturedContent(
                    url="https://example.com", title="升级前的笔记", text="原文"
                ).model_dump(mode="json"),
                key_points=[],
                suggested_tags=[],
                status="original_only",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["comments"]
            .insert()
            .values(
                id=1,
                note_id=1,
                content="升级前的评论",
                likes=10,
                replies=1,
                position=0,
            )
        )
        connection.execute(
            metadata.tables["capture_jobs"]
            .insert()
            .values(
                id="legacy-job",
                user_id=1,
                url="https://example.com",
                status="success",
                attempts=1,
                note_id=1,
                cached=False,
                created_at=now,
                updated_at=now,
            )
        )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
    note = client.get("/api/v1/notes/1", headers=auth).json()
    assert note["title"] == "升级前的笔记" and note["comment_score_error"] is None
    assert note["comments"][0]["ai_score"] is None
    assert note["comments"][0]["ai_reason"] is None
    assert note["comments"][0]["is_valuable"] is False
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        connection.execute(
            sa.text("UPDATE comments SET ai_score=0.8, ai_reason='依据', is_valuable=true")
        )
        command.downgrade(config, "0002_capture")
        assert (
            connection.scalar(sa.text("SELECT content FROM comments WHERE id=1")) == "升级前的评论"
        )
        assert connection.scalar(sa.text("SELECT title FROM notes WHERE id=1")) == "升级前的笔记"
        assert (
            connection.scalar(sa.text("SELECT note_id FROM capture_jobs WHERE id='legacy-job'"))
            == 1
        )
        assert "ai_score" not in {
            col["name"] for col in sa.inspect(connection).get_columns("comments")
        }
        command.upgrade(config, "head")
    restored = client.get("/api/v1/notes/1", headers=auth).json()
    assert restored["comments"][0]["ai_score"] is None
    assert restored["comments"][0]["is_valuable"] is False
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200


def test_postgresql_scoring_migration_ddl_without_deployment_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        secret_key="offline-migration-test-secret-at-least-32-chars",
        database_url="postgresql+psycopg://test:test@localhost/offline",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    output = StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "0002_capture:head", sql=True)
    upgrade = output.getvalue()
    assert "ADD COLUMN ai_score FLOAT" in upgrade
    assert "ADD COLUMN is_valuable BOOLEAN DEFAULT false NOT NULL" in upgrade
    assert "ADD COLUMN comment_score_error TEXT" in upgrade
    output.seek(0)
    output.truncate()
    command.downgrade(config, "head:0002_capture", sql=True)
    assert "DROP COLUMN ai_score" in output.getvalue()
    assert "DROP COLUMN comment_score_error" in output.getvalue()
