from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import jwt
import pytest
from app.db.base import utcnow
from app.models import RefreshToken, User
from app.security.credentials import hash_token, signing_key
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.conftest import ACCOUNT


def test_setup_is_single_use_and_passwords_are_hashed(client: TestClient, app: FastAPI) -> None:
    assert client.get("/api/v1/meta/version").json()["setup_completed"] is False
    first = client.post("/api/v1/setup", json=ACCOUNT)
    assert first.status_code == 201
    assert first.json()["user"]["is_admin"] is True
    assert first.json()["expires_in"] == 900
    assert client.get("/api/v1/meta/version").json()["setup_completed"] is True
    repeated = client.post("/api/v1/setup", json=ACCOUNT)
    assert repeated.status_code == 409
    with app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        assert ACCOUNT["password"] not in user.password_hash
        token = db.scalar(select(RefreshToken))
        assert token.token_hash == hash_token(first.json()["refresh_token"])
    assert first.headers["cache-control"] == "no-store"


def test_account_step_validation_does_not_create_or_claim_setup(
    client: TestClient, app: FastAPI
) -> None:
    response = client.post("/api/v1/setup/validate", json=ACCOUNT)
    assert response.status_code == 204
    assert client.get("/api/v1/meta/version").json()["setup_completed"] is False
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(User.id))) == 0
    created = client.post("/api/v1/setup", json=ACCOUNT)
    assert created.status_code == 201
    auth = {"Authorization": f"Bearer {created.json()['access_token']}"}
    assert client.get("/api/v1/settings", headers=auth).json()["llm"]["api_key_set"] is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("username", "name with space", "用户名"),
        ("email", "me@localhost", "邮箱"),
        ("password", "s3cr3t", "密码"),
    ],
)
def test_invalid_account_reports_the_field_before_ai_step(
    client: TestClient, field: str, value: str, message: str
) -> None:
    response = client.post("/api/v1/setup/validate", json={**ACCOUNT, field: value})
    assert response.status_code == 422
    error = response.json()["error"]
    assert message in error["message"]
    assert error["detail"]["fields"][0]["field"] == f"body.{field}"
    assert message in error["detail"]["fields"][0]["message"]
    assert value not in response.text
    assert ACCOUNT["password"] not in response.text
    assert client.get("/api/v1/meta/version").json()["setup_completed"] is False


@pytest.mark.parametrize(
    "llm",
    [None, {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "api_key": ""}],
)
def test_setup_does_not_require_an_ai_key(client: TestClient, llm: dict | None) -> None:
    response = client.post("/api/v1/setup", json={**ACCOUNT, "llm": llm})
    assert response.status_code == 201
    auth = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/api/v1/settings", headers=auth).json()["llm"]["api_key_set"] is False


def test_account_step_is_closed_after_initialization(client: TestClient, admin: dict) -> None:
    assert client.post("/api/v1/setup/validate", json=ACCOUNT).status_code == 409


def test_concurrent_setup_creates_exactly_one_admin(client: TestClient, app: FastAPI) -> None:
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: client.post("/api/v1/setup", json=ACCOUNT), range(2)))
    assert sorted(result.status_code for result in results) == [201, 409]
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(User.id))) == 1


def test_setup_failure_rolls_back_guard(client: TestClient, app: FastAPI, monkeypatch) -> None:
    from app.errors import ClipoError
    from app.services.auth import AuthService

    original = AuthService.create_user

    def fail(*args, **kwargs):
        raise ClipoError(409, "test_failure", "retry")

    monkeypatch.setattr(AuthService, "create_user", fail)
    assert client.post("/api/v1/setup", json=ACCOUNT).status_code == 409
    assert client.get("/api/v1/meta/version").json()["setup_completed"] is False
    monkeypatch.setattr(AuthService, "create_user", original)
    assert client.post("/api/v1/setup", json=ACCOUNT).status_code == 201


def test_registration_cannot_bypass_initialization(client: TestClient, app: FastAPI) -> None:
    app.state.settings.registration_open = True
    assert client.post("/api/v1/auth/register", json=ACCOUNT).status_code == 409


def test_registration_closed_by_default(client: TestClient, admin: dict) -> None:
    response = client.post("/api/v1/auth/register", json=ACCOUNT)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "registration_closed"


def test_open_registration_is_non_admin_and_normalizes_identity(
    client: TestClient, app: FastAPI, admin: dict
) -> None:
    app.state.settings.registration_open = True
    payload = {**ACCOUNT, "username": "Second", "email": "second@example.com", "is_admin": True}
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json()["user"]["is_admin"] is False
    assert response.json()["user"]["username"] == "second"
    duplicate = client.post("/api/v1/auth/register", json={**payload, "username": "SECOND"})
    assert duplicate.status_code == 409


def test_login_and_generic_invalid_credentials(client: TestClient, admin: dict) -> None:
    valid = client.post("/api/v1/auth/login", json={**ACCOUNT, "username": "ADMIN"})
    assert valid.status_code == 200
    wrong = client.post("/api/v1/auth/login", json={**ACCOUNT, "password": "wrong"})
    missing = client.post("/api/v1/auth/login", json={**ACCOUNT, "username": "unknown"})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()


def test_refresh_rotates_and_logout_revokes(client: TestClient, admin: dict) -> None:
    old = admin["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert rotated.status_code == 200
    fresh = rotated.json()["refresh_token"]
    assert fresh != old
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": old}).status_code == 401
    assert client.post("/api/v1/auth/logout", json={"refresh_token": fresh}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": fresh}).status_code == 401


def test_concurrent_refresh_allows_only_one_rotation(client: TestClient, admin: dict) -> None:
    payload = {"refresh_token": admin["refresh_token"]}
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: client.post("/api/v1/auth/refresh", json=payload), range(2))
        )
    assert sorted(response.status_code for response in results) == [200, 401]


def test_browser_session_uses_httponly_cookie(client: TestClient, admin: dict) -> None:
    login = client.post("/api/v1/auth/login", json=ACCOUNT)
    cookie = login.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v1/auth" in cookie
    refreshed = client.post("/api/v1/auth/refresh", json={})
    assert refreshed.status_code == 200
    assert client.post("/api/v1/auth/logout", json={}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={}).status_code == 401


def test_expired_refresh_is_rejected(client: TestClient, app: FastAPI, admin: dict) -> None:
    with app.state.session_factory.begin() as db:
        token = db.scalar(select(RefreshToken))
        token.expires_at = utcnow() - timedelta(seconds=1)
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": admin["refresh_token"]}
        ).status_code
        == 401
    )


def test_access_token_validation(client: TestClient, app: FastAPI, auth: dict) -> None:
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )
    expired = jwt.encode(
        {
            "sub": "1",
            "iat": utcnow() - timedelta(hours=1),
            "exp": utcnow() - timedelta(minutes=1),
            "iss": "clipo",
            "aud": "clipo-api",
            "type": "access",
        },
        signing_key(app.state.settings),
        algorithm="HS256",
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code
        == 401
    )


def test_errors_never_echo_sensitive_validation_input(client: TestClient) -> None:
    payload = {
        **ACCOUNT,
        "password": "secret",
        "llm": {"api_key": "sensitive-key", "max_comments": -1},
    }
    response = client.post("/api/v1/setup", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "secret" not in response.text and "sensitive-key" not in response.text
    assert client.get("/api/v1/missing").json()["error"]["code"] == "not_found"
    assert client.get("/api/v1/health").status_code == 200
