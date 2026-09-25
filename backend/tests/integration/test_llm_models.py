# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import socket
from collections.abc import Callable

import httpx
import pytest
from app.services import llm_models
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.conftest import ACCOUNT

BASE = "https://provider.example/v1"
KEY = "sk-offline-test-key"
PATH = "/api/v1/settings/llm/models"


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "model-b"},
                    {"id": "model-a"},
                    {"id": "model-a"},
                    {"id": ""},
                    {"id": 1},
                    {},
                    {"id": KEY},
                ]
            },
        )

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )
    monkeypatch.setattr(llm_models, "public_addresses", lambda url: ["93.184.216.34"])
    return requests


def test_models_preview_does_not_save_and_pins_connection(
    client: TestClient, auth: dict, provider: list[httpx.Request]
) -> None:
    before = client.get("/api/v1/settings", headers=auth).json()
    result = client.post(PATH, headers=auth, json={"base_url": BASE, "api_key": KEY})
    assert result.status_code == 200
    assert result.json() == {"models": ["model-a", "model-b"]}
    assert client.get("/api/v1/settings", headers=auth).json() == before
    assert len(provider) == 1
    request = provider[0]
    assert str(request.url) == "https://93.184.216.34/v1/models"
    assert request.method == "GET"
    assert request.headers["host"] == "provider.example"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert request.extensions["sni_hostname"] == "provider.example"


def test_saved_credentials_overrides_and_changed_destination(
    client: TestClient, auth: dict, app: FastAPI, provider: list[httpx.Request]
) -> None:
    client.put("/api/v1/settings", headers=auth, json={"llm": {"base_url": BASE, "api_key": KEY}})
    assert client.post(PATH, headers=auth, json={}).status_code == 200
    assert client.post(PATH, headers=auth, json={"base_url": BASE + "/"}).status_code == 200
    for payload in (
        {"base_url": "https://different.example/v1"},
        {"api_key": None},
        {"api_key": ""},
    ):
        assert client.post(PATH, headers=auth, json=payload).status_code == 422
    assert len(provider) == 2
    rejected = client.put(
        "/api/v1/settings", headers=auth, json={"llm": {"base_url": "https://different.example/v1"}}
    )
    assert rejected.status_code == 422
    assert client.get("/api/v1/settings", headers=auth).json()["llm"]["base_url"] == BASE
    app.state.settings.llm_base_url = BASE
    app.state.settings.llm_api_key = SecretStr("environment-secret")
    assert (
        client.post(
            PATH, headers=auth, json={"base_url": "https://ignored.example", "api_key": KEY}
        ).status_code
        == 200
    )
    assert provider[-1].headers["authorization"] == "Bearer environment-secret"
    app.state.settings.llm_base_url = None
    assert (
        client.post(
            PATH, headers=auth, json={"base_url": "https://different.example/v1", "api_key": KEY}
        ).status_code
        == 422
    )
    assert len(provider) == 3


def test_model_discovery_requires_auth_and_isolates_saved_key(
    client: TestClient, auth: dict, app: FastAPI, provider: list[httpx.Request]
) -> None:
    assert client.post(PATH, json={}).status_code == 401
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": KEY}})
    app.state.settings.registration_open = True
    other = client.post(
        "/api/v1/auth/register",
        json={**ACCOUNT, "username": "second", "email": "second@example.com"},
    ).json()
    assert (
        client.post(
            PATH, headers={"Authorization": "Bearer " + other["access_token"]}, json={}
        ).status_code
        == 422
    )
    assert not provider


@pytest.mark.parametrize(
    "url",
    [
        "http://provider.example/v1",
        "https://127.0.0.1/v1",
        "https://localhost/v1",
        "https://user:pass@provider.example/v1",
        "https://provider.example:8080/v1",
        "https://provider.example/v1?secret=test",
    ],
)
def test_models_reject_unsafe_urls(
    client: TestClient, auth: dict, provider: list[httpx.Request], url: str
) -> None:
    result = client.post(PATH, headers=auth, json={"base_url": url, "api_key": KEY})
    assert result.status_code == 422
    assert not provider


def test_models_validate_all_dns_records(
    client: TestClient, auth: dict, provider: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.security.urls import public_addresses

    monkeypatch.setattr(llm_models, "public_addresses", public_addresses)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
            for ip in ("93.184.216.34", "127.0.0.1")
        ],
    )
    assert (
        client.post(PATH, headers=auth, json={"base_url": BASE, "api_key": KEY}).status_code == 422
    )
    assert not provider


@pytest.mark.parametrize(
    "response",
    [
        lambda: httpx.Response(401, text=KEY),
        lambda: httpx.Response(403, text=KEY),
        lambda: httpx.Response(404, text=KEY),
        lambda: httpx.Response(429, text=KEY),
        lambda: httpx.Response(302, headers={"location": "https://evil.example"}),
        lambda: httpx.Response(200, json={"bad": KEY}),
        lambda: httpx.Response(200, text=KEY, headers={"content-type": "application/json"}),
        lambda: httpx.Response(
            200, text="x" * (4 * 1024 * 1024 + 1), headers={"content-type": "application/json"}
        ),
        lambda: httpx.Response(200, text="<html>not a catalog</html>"),
    ],
)
def test_model_errors_are_redacted_and_redirects_not_followed(
    client: TestClient,
    auth: dict,
    monkeypatch: pytest.MonkeyPatch,
    response: Callable[[], httpx.Response],
) -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response()

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )
    monkeypatch.setattr(llm_models, "public_addresses", lambda url: ["93.184.216.34"])
    result = client.post(PATH, headers=auth, json={"base_url": BASE, "api_key": KEY})
    assert result.status_code in (422, 502)
    assert KEY not in result.text
    assert len(calls) == 1
