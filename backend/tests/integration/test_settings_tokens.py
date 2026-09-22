# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from app.models import ApiToken, UserSettings
from app.security.credentials import decrypt_secret, hash_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.conftest import ACCOUNT


def test_tokens_are_hashed_listed_and_revocable(
    client: TestClient, app: FastAPI, auth: dict
) -> None:
    response = client.post("/api/v1/tokens", json={"name": "desktop"}, headers=auth)
    assert response.status_code == 201
    token = response.json()
    assert token["token"].startswith("ct_")
    listed = client.get("/api/v1/tokens", headers=auth)
    assert len(listed.json()) == 1
    assert "token" not in listed.json()[0]
    assert token["token"] not in listed.text
    assert listed.json()[0]["created_at"].endswith("Z")
    with app.state.session_factory() as db:
        stored = db.scalar(select(ApiToken))
        assert stored.token_hash == hash_token(token["token"])
    token_headers = {"X-Clipo-Token": token["token"]}
    assert client.get("/api/v1/auth/me", headers=token_headers).status_code == 200
    assert client.get("/api/v1/tokens", headers=auth).json()[0]["last_used_at"] is not None
    assert client.delete(f"/api/v1/tokens/{token['id']}", headers=auth).status_code == 204
    assert client.get("/api/v1/auth/me", headers=token_headers).status_code == 401


def test_settings_encrypt_secrets_preserve_omissions_and_clear_null(
    client: TestClient, app: FastAPI, auth: dict
) -> None:
    secret = "sk-never-echo-this"
    response = client.put(
        "/api/v1/settings",
        json={"llm": {"api_key": secret, "model": "deepseek-chat"}},
        headers=auth,
    )
    assert response.status_code == 200
    assert response.json()["llm"]["api_key_set"] is True
    assert secret not in response.text
    with app.state.session_factory() as db:
        value = db.get(UserSettings, 1).llm_config["api_key"]
        assert secret not in value
        assert decrypt_secret(value, app.state.settings) == secret
    assert (
        client.put("/api/v1/settings", json={"llm": {"model": "qwen-plus"}}, headers=auth).json()[
            "llm"
        ]["api_key_set"]
        is True
    )
    assert (
        client.put("/api/v1/settings", json={"llm": {"api_key": None}}, headers=auth).json()["llm"][
            "api_key_set"
        ]
        is False
    )
    assert client.get("/api/v1/meta/capabilities", headers=auth).json()["capture_available"] is True


def test_setup_encrypts_optional_llm_config(client: TestClient, app: FastAPI) -> None:
    secret = "sk-setup-secret"
    response = client.post("/api/v1/setup", json={**ACCOUNT, "llm": {"api_key": secret}})
    assert response.status_code == 201
    with app.state.session_factory() as db:
        value = db.get(UserSettings, 1).llm_config["api_key"]
        assert decrypt_secret(value, app.state.settings) == secret


def test_settings_and_tokens_are_isolated_by_user(
    client: TestClient, app: FastAPI, auth: dict
) -> None:
    app.state.settings.registration_open = True
    token = client.post("/api/v1/tokens", headers=auth, json={"name": "private"}).json()
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={"llm": {"model": "owner-model", "api_key": "owner-secret"}},
    )
    second = client.post(
        "/api/v1/auth/register",
        json={**ACCOUNT, "username": "second", "email": "second@example.com"},
    ).json()
    other_auth = {"Authorization": f"Bearer {second['access_token']}"}
    assert client.get("/api/v1/tokens", headers=other_auth).json() == []
    assert client.delete(f"/api/v1/tokens/{token['id']}", headers=other_auth).status_code == 404
    settings = client.get("/api/v1/settings", headers=other_auth).json()["llm"]
    assert settings["model"] == "qwen-plus" and settings["api_key_set"] is False
    assert client.get("/api/v1/tokens", headers=auth).json()[0]["name"] == "private"


def test_environment_overrides_database_and_defaults(
    client: TestClient, app: FastAPI, auth: dict
) -> None:
    from pydantic import SecretStr

    client.put("/api/v1/settings", headers=auth, json={"llm": {"model": "database-model"}})
    assert client.get("/api/v1/settings", headers=auth).json()["llm"]["model"] == "database-model"
    app.state.settings.llm_model = "environment-model"
    app.state.settings.llm_api_key = SecretStr("environment-secret")
    response = client.get("/api/v1/settings", headers=auth)
    assert response.json()["llm"]["model"] == "environment-model"
    assert response.json()["llm"]["api_key_set"] is True
    assert "api_key" in response.json()["llm"]["overridden_fields"]
    assert "environment-secret" not in response.text
