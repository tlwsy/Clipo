from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT, Settings
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ACCOUNT = {"username": "admin", "email": "admin@example.com", "password": "correct-horse-battery"}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--postgres-url", default=None, help="隔离 schema 的 PostgreSQL 集成测试连接")


@pytest.fixture
def app(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[FastAPI]:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    postgres_url = request.config.getoption("--postgres-url")
    admin_engine = None
    schema = "clipo_test_" + uuid4().hex
    if postgres_url:
        admin_engine = create_engine(postgres_url, hide_parameters=True)
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        database_url = (
            make_url(postgres_url)
            .update_query_dict({"options": f"-csearch_path={schema},public"})
            .render_as_string(hide_password=False)
        )
    settings = Settings(
        _env_file=None,
        secret_key="test-only-secret-key-at-least-32-characters",
        database_url=database_url,
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
    if admin_engine is not None:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


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
