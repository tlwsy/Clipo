# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from io import StringIO

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT, Settings
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_capture_settings_upgrade_and_rollback_preserve_existing_configuration(
    app: FastAPI, client: TestClient, auth: dict[str, str]
) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "llm": {"api_key": "offline-model-key"},
            "platform_cookies": {"xiaohongshu": "session=offline"},
        },
    )
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0003_comment_scoring")
        before = connection.execute(
            sa.text(
                "SELECT llm_config, platform_cookies, media_policy, backup_config "
                "FROM user_settings WHERE user_id=1"
            )
        ).one()
        assert "capture_config" not in {
            column["name"] for column in sa.inspect(connection).get_columns("user_settings")
        }
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        assert (
            connection.scalar(sa.text("SELECT capture_config FROM user_settings WHERE user_id=1"))
            == "{}"
        )
    assert client.get("/api/v1/settings", headers=auth).json()["capture"]["max_comments"] == 100
    client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": 0}})
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0003_comment_scoring")
        after = connection.execute(
            sa.text(
                "SELECT llm_config, platform_cookies, media_policy, backup_config "
                "FROM user_settings WHERE user_id=1"
            )
        ).one()
        assert after == before
        command.upgrade(config, "head")
    restored = client.get("/api/v1/settings", headers=auth).json()
    assert restored["capture"]["max_comments"] == 100
    assert restored["llm"]["api_key_set"] is True
    assert restored["platform_cookies"]["xiaohongshu"]["cookie_set"] is True
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200


def test_postgresql_capture_settings_migration_ddl(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        secret_key="offline-migration-test-secret-at-least-32-chars",
        database_url="postgresql+psycopg://test:test@localhost/offline",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    output = StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "0003_comment_scoring:head", sql=True)
    assert "ADD COLUMN capture_config JSONB DEFAULT '{}' NOT NULL" in output.getvalue()
    output.seek(0)
    output.truncate()
    command.downgrade(config, "head:0003_comment_scoring", sql=True)
    assert "DROP COLUMN capture_config" in output.getvalue()
