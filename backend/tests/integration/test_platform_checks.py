# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import timedelta

import pytest
from app.db.base import utcnow
from app.extractors.base import ExtractionError, LoginExpiredError
from app.extractors.xhs_api import XhsClient
from app.extractors.xiaoheihe import HeyboxClient
from app.models import PlatformCheck
from app.platform_repository import PlatformCheckRepository
from app.tasks.capture import CaptureQueue
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.conftest import ACCOUNT

PATH = "/api/v1/settings/platform-checks"


def configure(client: TestClient, auth: dict[str, str], cookie: str = "session=offline") -> None:
    response = client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "platform_cookies": {"xiaohongshu": cookie, "xiaoheihe": cookie},
        },
    )
    assert response.status_code == 200


def execute(app: FastAPI) -> None:
    huey = app.state.capture_queue.huey
    huey.execute(huey.dequeue())


def test_checks_require_auth_cookie_and_known_platform(
    client: TestClient, auth: dict[str, str]
) -> None:
    assert client.get(PATH).status_code == 401
    assert client.post(PATH + "/xiaohongshu").status_code == 401
    assert client.post(PATH + "/unknown", headers=auth).status_code == 422
    assert client.post(PATH + "/xiaohongshu", headers=auth).status_code == 409
    assert client.get(PATH, headers=auth).json()["xiaohongshu"]["status"] == "unconfigured"


@pytest.mark.parametrize("platform,cls", [("xiaohongshu", XhsClient), ("xiaoheihe", HeyboxClient)])
def test_check_is_background_deduplicated_and_persists_no_secret(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    cls: type,
) -> None:
    configure(client, auth)
    calls = []

    def probe(self: object) -> bool:
        calls.append(self.cookie.value.get_secret_value())
        return True

    monkeypatch.setattr(cls, "check_login", probe)
    for _ in range(2):
        response = client.post(PATH + "/" + platform, headers=auth)
        assert response.status_code == 202 and response.json()["status"] == "queued"
    assert calls == []
    huey = app.state.capture_queue.huey
    assert b"session=offline" not in b"".join(huey.storage.enqueued_items())
    execute(app)
    execute(app)
    assert calls == ["session=offline"]
    status = client.get(PATH, headers=auth)
    assert status.json()[platform]["status"] == "valid"
    assert status.json()[platform]["checked_at"] is not None
    assert "offline" not in status.text and "credential_hash" not in status.text
    with app.state.session_factory() as db:
        row = db.get(PlatformCheck, (1, platform))
        assert "offline" not in str(row.__dict__)


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (False, "invalid"),
        (LoginExpiredError("expired"), "invalid"),
        (ExtractionError("需要浏览器验证", False), "error"),
        (ExtractionError("请求过于频繁"), "error"),
        (RuntimeError("private-secret"), "error"),
    ],
)
def test_uncertain_results_never_become_invalid(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    outcome: object,
    expected: str,
) -> None:
    configure(client, auth)

    def probe(self: object) -> bool:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(XhsClient, "check_login", probe)
    client.post(PATH + "/xiaohongshu", headers=auth)
    execute(app)
    response = client.get(PATH, headers=auth)
    assert response.json()["xiaohongshu"]["status"] == expected
    assert "private-secret" not in response.text


@pytest.mark.parametrize("new_cookie", ["session=replaced", None])
def test_cookie_replacement_or_clear_fences_inflight_result(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    new_cookie: str | None,
) -> None:
    configure(client, auth)

    def probe(self: object) -> bool:
        client.put(
            "/api/v1/settings", headers=auth, json={"platform_cookies": {"xiaohongshu": new_cookie}}
        )
        return True

    monkeypatch.setattr(XhsClient, "check_login", probe)
    client.post(PATH + "/xiaohongshu", headers=auth)
    execute(app)
    status = client.get(PATH, headers=auth).json()["xiaohongshu"]
    assert status["status"] == ("unverified" if new_cookie else "unconfigured")
    assert status["checked_at"] is None


def test_new_request_and_account_cannot_be_overwritten_by_stale_worker(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
) -> None:
    configure(client, auth)
    app.state.settings.registration_open = True
    other = client.post(
        "/api/v1/auth/register", json={**ACCOUNT, "username": "other", "email": "other@example.com"}
    ).json()
    other_auth = {"Authorization": f"Bearer {other['access_token']}"}
    configure(client, other_auth, "session=other")
    with app.state.session_factory.begin() as db:
        repo = PlatformCheckRepository(db, 1)
        row = repo.request("xiaohongshu")
        request_id = row.request_id
        assert repo.claim("xiaohongshu", request_id, "old")
        assert not PlatformCheckRepository(db, other["user"]["id"]).claim(
            "xiaohongshu", request_id, "intruder"
        )
        row.lease_expires_at = utcnow() - timedelta(seconds=1)
    with app.state.session_factory.begin() as db:
        repo = PlatformCheckRepository(db, 1)
        assert repo.claim("xiaohongshu", request_id, "new")
        repo.finish("xiaohongshu", request_id, "new", "invalid", "expired")
        repo.finish("xiaohongshu", request_id, "old", "valid", "must-not-save")
    assert client.get(PATH, headers=auth).json()["xiaohongshu"]["status"] == "invalid"
    assert client.get(PATH, headers=other_auth).json()["xiaohongshu"]["status"] == "unverified"


def test_recovery_dispatches_committed_checks_and_exhausts_interrupted_leases(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(client, auth)
    with app.state.session_factory.begin() as db:
        PlatformCheckRepository(db, 1).request("xiaohongshu")
    queue = CaptureQueue(app.state.session_factory, app.state.settings)
    monkeypatch.setattr(XhsClient, "check_login", lambda self: True)
    queue.recover()
    queue.huey.execute(queue.huey.dequeue())
    assert client.get(PATH, headers=auth).json()["xiaohongshu"]["status"] == "valid"
    with app.state.session_factory.begin() as db:
        repo = PlatformCheckRepository(db, 1)
        row = repo.request("xiaohongshu")
        row.status = "running"
        row.attempts = 3
        row.lease_expires_at = utcnow() - timedelta(seconds=1)
    queue.recover()
    assert client.get(PATH, headers=auth).json()["xiaohongshu"]["status"] == "error"
