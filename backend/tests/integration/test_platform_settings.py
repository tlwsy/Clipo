import logging

import pytest
from app.models import UserSettings
from app.security.credentials import decrypt_secret
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.conftest import ACCOUNT


def test_cookie_settings_encrypt_secrets_and_only_return_status(
    client: TestClient, app: FastAPI, auth: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    cookies = {
        "xiaohongshu": "web_session=private-xhs-session; a1=private-device",
        "xiaoheihe": "session=private-heybox-session==; empty=",
    }
    response = client.put("/api/v1/settings", headers=auth, json={"platform_cookies": cookies})
    assert response.status_code == 200
    expected = {platform: {"cookie_set": True} for platform in cookies}
    assert response.json()["platform_cookies"] == expected
    read = client.get("/api/v1/settings", headers=auth)
    assert read.json()["platform_cookies"] == expected
    assert read.headers["Cache-Control"] == "no-store"
    with app.state.session_factory() as db:
        stored = db.get(UserSettings, 1).platform_cookies
        for platform, secret in cookies.items():
            assert decrypt_secret(stored[platform], app.state.settings) == secret
            assert secret not in str(stored)
            assert stored[platform] not in read.text + response.text
            assert secret not in read.text + response.text + caplog.text


def test_cookie_updates_preserve_omissions_replace_and_clear_one_platform(
    client: TestClient, app: FastAPI, auth: dict[str, str]
) -> None:
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "llm": {"api_key": "private-model-key"},
            "platform_cookies": {"xiaohongshu": "session=first", "xiaoheihe": "session=other"},
        },
    )
    with app.state.session_factory() as db:
        original = dict(db.get(UserSettings, 1).platform_cookies)
    for payload in ({}, {"platform_cookies": {}}, {"platform_cookies": None}, {"llm": {}}):
        response = client.put("/api/v1/settings", headers=auth, json=payload)
        assert response.status_code == 200
        with app.state.session_factory() as db:
            assert db.get(UserSettings, 1).platform_cookies == original
    response = client.put(
        "/api/v1/settings",
        headers=auth,
        json={"platform_cookies": {"xiaohongshu": " session=replaced== "}},
    )
    assert response.json()["llm"]["api_key_set"] is True
    with app.state.session_factory() as db:
        stored = db.get(UserSettings, 1).platform_cookies
        assert decrypt_secret(stored["xiaohongshu"], app.state.settings) == "session=replaced=="
        assert stored["xiaoheihe"] == original["xiaoheihe"]
    client.put("/api/v1/settings", headers=auth, json={"platform_cookies": {"xiaohongshu": None}})
    status = client.get("/api/v1/settings", headers=auth).json()["platform_cookies"]
    assert status == {"xiaohongshu": {"cookie_set": False}, "xiaoheihe": {"cookie_set": True}}
    client.put("/api/v1/settings", headers=auth, json={"platform_cookies": {"xiaoheihe": ""}})
    with app.state.session_factory() as db:
        stored = db.get(UserSettings, 1)
        assert stored.platform_cookies == {}
        assert (
            decrypt_secret(stored.llm_config["api_key"], app.state.settings) == "private-model-key"
        )


def test_cookie_settings_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/settings").status_code == 401
    assert (
        client.put(
            "/api/v1/settings", json={"platform_cookies": {"xiaohongshu": "a=b"}}
        ).status_code
        == 401
    )


def test_cookie_settings_are_isolated_by_user(
    client: TestClient, app: FastAPI, auth: dict[str, str]
) -> None:
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={"platform_cookies": {"xiaohongshu": "session=owner"}},
    )
    app.state.settings.registration_open = True
    second = client.post(
        "/api/v1/auth/register",
        json={**ACCOUNT, "username": "second", "email": "second@example.com"},
    ).json()
    other_auth = {"Authorization": f"Bearer {second['access_token']}"}
    assert client.get("/api/v1/settings", headers=other_auth).json()["platform_cookies"] == {
        "xiaohongshu": {"cookie_set": False},
        "xiaoheihe": {"cookie_set": False},
    }
    client.put(
        "/api/v1/settings",
        headers=other_auth,
        json={"platform_cookies": {"xiaohongshu": "session=second", "xiaoheihe": "session=other"}},
    )
    client.put(
        "/api/v1/settings", headers=other_auth, json={"platform_cookies": {"xiaohongshu": None}}
    )
    with app.state.session_factory() as db:
        owner = db.get(UserSettings, 1).platform_cookies
        other = db.get(UserSettings, second["user"]["id"]).platform_cookies
        assert decrypt_secret(owner["xiaohongshu"], app.state.settings) == "session=owner"
        assert "xiaoheihe" not in owner
        assert "xiaohongshu" not in other


@pytest.mark.parametrize(
    "cookies",
    [
        {"xiaohongshu": "session=private\r\nX-Injected: yes"},
        {"xiaoheihe": "session=private\n"},
        {"xiaohongshu": "session=private\x00"},
        {"xiaohongshu": "session=private\x7f"},
        {"xiaoheihe": "session=private非ASCII"},
        {"xiaohongshu": "Cookie: session=private"},
        {"xiaohongshu": "Set-Cookie: session=private"},
        {"xiaohongshu": "session=private; missing-pair"},
        {"xiaohongshu": "session=private; =nameless"},
        {"xiaohongshu": "session=" + "x" * 16377},
        {"xiaohongshu": "   "},
        {"xiaohongshu": 42},
        {"unsupported": "session=private"},
    ],
    ids=[
        "crlf",
        "newline",
        "null-byte",
        "del",
        "unicode",
        "header-prefix",
        "response-header",
        "missing-pair",
        "missing-name",
        "oversized",
        "whitespace",
        "non-string",
        "unknown-platform",
    ],
)
def test_invalid_cookie_is_redacted_and_does_not_partially_update_settings(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    cookies: dict[str, str | int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    client.put(
        "/api/v1/settings", headers=auth, json={"platform_cookies": {"xiaohongshu": "session=old"}}
    )
    response = client.put(
        "/api/v1/settings",
        headers=auth,
        json={"llm": {"model": "must-not-save"}, "platform_cookies": cookies},
    )
    assert response.status_code == 422
    assert "private" not in response.text + caplog.text
    assert "xxxxx" not in response.text + caplog.text
    assert "input" not in response.json()["error"]["detail"]["fields"][0]
    assert "Cookie" in response.json()["error"]["message"]
    with app.state.session_factory() as db:
        stored = db.get(UserSettings, 1)
        assert (
            decrypt_secret(stored.platform_cookies["xiaohongshu"], app.state.settings)
            == "session=old"
        )
        assert stored.llm_config == {}
