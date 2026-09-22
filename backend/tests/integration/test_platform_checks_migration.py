# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from io import StringIO

import pytest
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT, Settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text


def test_check_migration_preserves_account_settings_and_rolls_back(
    app: FastAPI,
    client: TestClient,
    auth: dict[str, str],
) -> None:
    client.put(
        "/api/v1/settings", headers=auth, json={"platform_cookies": {"xiaohongshu": "a=offline"}}
    )
    client.post("/api/v1/settings/platform-checks/xiaohongshu", headers=auth)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        original = connection.scalar(
            text("SELECT platform_cookies FROM user_settings WHERE user_id=1")
        )
        command.downgrade(config, "0004_capture_settings")
        assert "platform_checks" not in inspect(connection).get_table_names()
        assert (
            connection.scalar(text("SELECT platform_cookies FROM user_settings WHERE user_id=1"))
            == original
        )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
    status = client.get("/api/v1/settings/platform-checks", headers=auth).json()
    assert status["xiaohongshu"]["status"] == "unverified"
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200


def test_platform_checks_postgresql_ddl(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        secret_key="test-secret-for-offline-migration-32-chars",
        database_url="postgresql+psycopg://test:test@localhost/offline",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    output = StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "0004_capture_settings:head", sql=True)
    assert "CREATE TABLE platform_checks" in output.getvalue()
    assert "TIMESTAMP WITH TIME ZONE" in output.getvalue()
    output.seek(0)
    output.truncate()
    command.downgrade(config, "head:0004_capture_settings", sql=True)
    assert "DROP TABLE platform_checks" in output.getvalue()
