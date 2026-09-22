# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect


def test_upgrade_is_repeatable_preserves_accounts_and_matches_models(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
    assert client.get("/api/v1/auth/me", headers=auth).json()["username"] == "admin"


def test_migration_downgrade_and_reupgrade(app: FastAPI, client: TestClient) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert "users" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
    assert client.get("/api/v1/meta/version").json()["setup_completed"] is False
