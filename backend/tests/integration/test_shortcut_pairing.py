# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from urllib.parse import unquote, urlsplit

import pytest
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT, Settings
from app.db.base import utcnow
from app.models import ApiToken, ShortcutPairing
from app.security.credentials import hash_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

PAIRINGS = "/api/v1/shortcuts/pairings"
SERVER = "http://192.168.137.1:18000"


def issue(client: TestClient, auth: dict, **changes: object) -> dict:
    response = client.post(
        PAIRINGS, headers=auth, json={"name": "测试 iPhone", "server_url": SERVER, **changes}
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def code(pairing: dict) -> str:
    return json.loads(pairing["setup_input"].removeprefix("clipo-setup:"))["code"]


def test_pairing_creates_device_token_only_when_claimed_and_supports_revoke(
    client: TestClient, app: FastAPI, auth: dict
) -> None:
    pairing = issue(client, auth)
    assert client.get("/api/v1/tokens", headers=auth).json() == []
    launch = urlsplit(pairing["launch_url"])
    assert launch.scheme == "shortcuts" and launch.netloc == "run-shortcut"
    # Shortcuts decodes percent escapes, leaving form-encoded '+' characters literal.
    launch_parameters = {
        unquote(key): unquote(value)
        for key, value in (parameter.split("=", 1) for parameter in launch.query.split("&"))
    }
    assert " " not in launch.query
    assert launch_parameters == {
        "name": "保存到 Clipo",
        "input": "text",
        "text": pairing["setup_input"],
    }
    with app.state.session_factory() as db:
        row = db.get(ShortcutPairing, 1)
        assert row.code_hash == hash_token(code(pairing))
        assert 290 < (row.expires_at - utcnow()).total_seconds() <= 300
        assert row.token_id is None
    status = client.get(PAIRINGS + "/" + pairing["id"], headers=auth)
    assert status.json()["status"] == "pending"
    assert code(pairing) not in status.text and "setup_input" not in status.text
    claimed = client.post(PAIRINGS + "/consume", json={"code": code(pairing)})
    assert claimed.status_code == 200
    assert claimed.headers["cache-control"] == "no-store"
    config = claimed.json()
    assert config["server_url"] == SERVER and config["version"] == 1
    token_auth = {"X-Clipo-Token": config["token"]}
    assert client.get("/api/v1/auth/me", headers=token_auth).json()["id"] == 1
    assert (
        client.post(
            "/api/v1/captures", headers=token_auth, json={"url": "https://example.com/ios"}
        ).status_code
        == 202
    )
    assert client.get(PAIRINGS + "/" + pairing["id"], headers=auth).json()["status"] == "claimed"
    assert client.post(PAIRINGS + "/consume", json={"code": code(pairing)}).status_code == 400
    assert client.delete(PAIRINGS + "/" + pairing["id"], headers=auth).status_code == 409
    assert client.delete(f"/api/v1/tokens/{config['token_id']}", headers=auth).status_code == 204
    assert client.get(PAIRINGS + "/" + pairing["id"], headers=auth).json()["status"] == "revoked"
    assert client.get("/api/v1/auth/me", headers=token_auth).status_code == 401


def test_new_code_invalidates_previous_and_cancel_expiry_are_final(
    client: TestClient, app: FastAPI, auth: dict
) -> None:
    old = issue(client, auth)
    current = issue(client, auth)
    assert client.post(PAIRINGS + "/consume", json={"code": code(old)}).status_code == 400
    assert client.get(PAIRINGS + "/" + old["id"], headers=auth).status_code == 404
    with app.state.session_factory.begin() as db:
        assert db.scalar(select(func.count()).select_from(ShortcutPairing)) == 1
        db.execute(update(ShortcutPairing).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert client.get(PAIRINGS + "/" + current["id"], headers=auth).json()["status"] == "expired"
    expired = client.post(PAIRINGS + "/consume", json={"code": code(current)})
    assert expired.status_code == 400 and code(current) not in expired.text
    latest = issue(client, auth)
    assert client.delete(PAIRINGS + "/" + latest["id"], headers=auth).status_code == 204
    assert client.post(PAIRINGS + "/consume", json={"code": code(latest)}).status_code == 400
    assert client.get("/api/v1/tokens", headers=auth).json() == []


def test_pairings_are_account_scoped(client: TestClient, app: FastAPI, auth: dict) -> None:
    pairing = issue(client, auth)
    assert client.post(PAIRINGS, json={"name": "guest", "server_url": SERVER}).status_code == 401
    app.state.settings.registration_open = True
    other = client.post(
        "/api/v1/auth/register",
        json={"username": "other", "email": "other@example.com", "password": "other-password-123"},
    ).json()
    other_auth = {"Authorization": "Bearer " + other["access_token"]}
    path = PAIRINGS + "/" + pairing["id"]
    assert client.get(path, headers=other_auth).status_code == 404
    assert client.delete(path, headers=other_auth).status_code == 409
    second = issue(client, other_auth)
    claimed = client.post(PAIRINGS + "/consume", json={"code": code(pairing)}).json()
    assert len(client.get("/api/v1/tokens", headers=auth).json()) == 1
    assert client.get("/api/v1/tokens", headers=other_auth).json() == []
    assert (
        client.delete(f"/api/v1/tokens/{claimed['token_id']}", headers=other_auth).status_code
        == 404
    )
    assert (
        client.get(PAIRINGS + "/" + second["id"], headers=other_auth).json()["status"] == "pending"
    )


@pytest.mark.parametrize(
    "origin",
    [
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?code=secret",
        "https://example.com#secret",
        "javascript:alert(1)",
        "http://example.com",
        "http://0.0.0.0",
        "http://224.0.0.1",
    ],
)
def test_pairing_rejects_unsafe_server_address_without_echoing_input(
    client: TestClient, auth: dict, origin: str
) -> None:
    response = client.post(PAIRINGS, headers=auth, json={"name": "phone", "server_url": origin})
    assert response.status_code == 422 and origin not in response.text


def test_http_lan_and_https_origins_normalize(client: TestClient, auth: dict) -> None:
    for origin in [
        SERVER,
        "http://localhost:8000",
        "http://[::1]:8000",
        "https://clipo.example.com",
    ]:
        pairing = issue(client, auth, server_url=origin + "/")
        assert json.loads(pairing["setup_input"][len("clipo-setup:") :])["server_url"] == origin
    denied = client.post(PAIRINGS + "/consume", json={"code": "secret-invalid-input"})
    assert denied.status_code == 422 and "secret-invalid-input" not in denied.text


def test_concurrent_claims_issue_exactly_one_token(
    client: TestClient, app: FastAPI, auth: dict
) -> None:
    pairing = issue(client, auth)
    barrier = Barrier(2)

    def claim() -> int:
        # A separate client/session per thread exercises the database's atomic condition.
        with TestClient(app) as parallel:
            barrier.wait(timeout=10)
            return parallel.post(PAIRINGS + "/consume", json={"code": code(pairing)}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sorted(results) == [200, 400]
    assert len(client.get("/api/v1/tokens", headers=auth).json()) == 1


def test_token_creation_failure_rolls_back_code_consumption(
    client: TestClient, app: FastAPI, auth: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.errors import ClipoError
    from app.services import shortcuts

    pairing = issue(client, auth)
    original = shortcuts.issue_token

    def fail(*args: object) -> None:
        raise ClipoError(503, "test_failure", "测试失败")

    monkeypatch.setattr(shortcuts, "issue_token", fail)
    assert client.post(PAIRINGS + "/consume", json={"code": code(pairing)}).status_code == 503
    monkeypatch.setattr(shortcuts, "issue_token", original)
    assert client.post(PAIRINGS + "/consume", json={"code": code(pairing)}).status_code == 200


def test_pairing_migration_roundtrip_preserves_issued_tokens(
    client: TestClient, app: FastAPI, auth: dict
) -> None:
    pairing = issue(client, auth)
    claimed = client.post(PAIRINGS + "/consume", json={"code": code(pairing)}).json()
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0008_stable_note_ids")
        command.upgrade(config, "head")
        command.check(config)
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ShortcutPairing)) == 0
        assert db.get(ApiToken, claimed["token_id"]) is not None


def test_only_validated_icloud_url_is_advertised(client: TestClient, app: FastAPI) -> None:
    assert client.get("/api/v1/shortcuts/info").json()["install_url"] is None
    url = "https://www.icloud.com/shortcuts/" + "a" * 32
    settings = Settings(
        _env_file=None,
        secret_key="test-only-long-secret-at-least-32-characters",
        shortcut_install_url=url,
    )
    app.state.settings.shortcut_install_url = settings.shortcut_install_url
    assert client.get("/api/v1/shortcuts/info").json()["install_url"] == url
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            secret_key="test-only-long-secret-at-least-32-characters",
            shortcut_install_url="https://untrusted.example/shortcut",
        )
