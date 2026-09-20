from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT, Settings
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient

ACCOUNT = {"username": "admin", "email": "admin@example.com", "password": "correct-horse-battery"}


@pytest.fixture
def app(tmp_path: Path) -> Iterator[FastAPI]:
    settings = Settings(
        _env_file=None,
        secret_key="test-only-secret-key-at-least-32-characters",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        static_path=tmp_path / "static",
        queue_path=tmp_path / "huey.db",
    )
    application = create_app(settings)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield application
    application.state.engine.dispose()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin(client: TestClient) -> dict:
    response = client.post("/api/v1/setup", json=ACCOUNT)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def auth(admin: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin['access_token']}"}
