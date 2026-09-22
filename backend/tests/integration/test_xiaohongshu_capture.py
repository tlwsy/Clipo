# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from app.extractors import xiaohongshu
from app.models import Note, UserSettings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.conftest import ACCOUNT

FIXTURES = Path(__file__).parents[1] / "fixtures"
HTML = (FIXTURES / "xiaohongshu.html").read_text()
URL = "https://www.xiaohongshu.com/explore/64abc123"


def submit(client: TestClient, auth: dict[str, str]) -> str:
    response = client.post("/api/v1/captures", headers=auth, json={"url": URL})
    assert response.status_code == 202
    return response.json()["job_id"]


@pytest.fixture
def offline_xhs(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    cookies: list[str | None] = []

    def fetch(url: str, **kwargs: Any) -> tuple[str, str]:
        cookie = kwargs.get("cookie")
        secret = cookie.value.get_secret_value() if cookie else None
        cookies.append(secret)
        html = (
            (FIXTURES / "xiaohongshu-login.html").read_text()
            if secret == "session=expired"
            else HTML
        )
        return html, url

    monkeypatch.setattr(xiaohongshu, "fetch_html", fetch)
    return cookies


def test_xhs_job_uses_owner_cookie_saves_comments_and_reuses_own_cache(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    offline_xhs: list[str | None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "platform_cookies": {
                "xiaohongshu": "session=owner-private",
                "xiaoheihe": "session=other-platform-private",
            }
        },
    )
    job_id = submit(client, auth)
    huey = app.state.capture_queue.huey
    huey.execute(huey.dequeue())
    job = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()
    assert job["status"] == "success" and job["attempts"] == 1
    response = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth)
    note = response.json()
    assert note["source"]["platform"] == "xiaohongshu"
    assert note["source"]["author"] == "离线作者"
    assert note["content"]["raw_html"] is None
    assert len(note["content"]["images"]) == 2
    assert len(note["comments"]) == 10
    assert note["comments"][0]["likes"] == 12
    assert note["status"] == "original_only"
    assert "未生成摘要" in note["summary_error"]
    with app.state.session_factory() as db:
        assert db.get(Note, note["id"]).content["raw_html"] == HTML
    client.put("/api/v1/settings", headers=auth, json={"platform_cookies": {"xiaohongshu": None}})
    cached_id = submit(client, auth)
    huey.execute(huey.dequeue())
    assert client.get(f"/api/v1/jobs/{cached_id}", headers=auth).json()["cached"]
    assert offline_xhs == ["session=owner-private"]
    assert "private" not in response.text + caplog.text


def test_expired_cookie_is_terminal_and_manual_retry_reads_replacement(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    offline_xhs: list[str | None],
) -> None:
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={"platform_cookies": {"xiaohongshu": "session=expired"}},
    )
    job_id = submit(client, auth)
    pipeline = app.state.capture_queue.pipeline
    assert pipeline.run(1, job_id) is None
    job = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()
    assert job["status"] == "failed" and job["next_retry_at"] is None
    assert "登录态失效" in job["last_error"]
    assert client.get("/api/v1/notes", headers=auth).json()["items"] == []
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "platform_cookies": {"xiaohongshu": "session=replaced"},
            "capture": {"max_comments": 4},
        },
    )
    assert client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth).status_code == 202
    pipeline.run(1, job_id)
    job = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()
    assert job["status"] == "success"
    note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()
    assert len(note["comments"]) == 4 and note["content"]["comment_capture_limit"] == 4
    assert offline_xhs == ["session=expired", "session=replaced"]


def test_user_cookie_and_cache_are_isolated_in_concurrent_worker_runs(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.state.settings.registration_open = True
    second = client.post(
        "/api/v1/auth/register",
        json={
            **ACCOUNT,
            "username": "second",
            "email": "second@example.com",
        },
    ).json()
    other_auth = {"Authorization": "Bearer " + second["access_token"]}
    for headers, value in [(auth, "first"), (other_auth, "second")]:
        client.put(
            "/api/v1/settings",
            headers=headers,
            json={
                "platform_cookies": {"xiaohongshu": f"session={value}"},
                "capture": {"max_comments": 1 if value == "first" else 5},
            },
        )
    jobs = [(1, submit(client, auth)), (second["user"]["id"], submit(client, other_auth))]
    barrier = Barrier(2)

    def fetch(url: str, **kwargs: Any) -> tuple[str, str]:
        cookie = kwargs["cookie"].value.get_secret_value()
        barrier.wait(timeout=10)
        return HTML.replace("离线作者", cookie.removeprefix("session=")), url

    monkeypatch.setattr(xiaohongshu, "fetch_html", fetch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: app.state.capture_queue.pipeline.run(*args), jobs))
    assert results == [None, None]
    for headers, (_, job_id), expected in [
        (auth, jobs[0], "first"),
        (other_auth, jobs[1], "second"),
    ]:
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        assert job["status"] == "success" and job["cached"] is False
        note = client.get(f"/api/v1/notes/{job['note_id']}", headers=headers).json()
        assert note["source"]["author"] == expected
        assert len(note["comments"]) == (1 if expected == "first" else 5)
        # Subsequent captures use only this user's own cache.
        cached_job = submit(client, headers)
        user_id = jobs[0][0] if headers == auth else jobs[1][0]
        app.state.capture_queue.pipeline.run(user_id, cached_job)
        cached = client.get(f"/api/v1/jobs/{cached_job}", headers=headers).json()
        assert cached["cached"]
        note = client.get(f"/api/v1/notes/{cached['note_id']}", headers=headers).json()
        assert note["source"]["author"] == expected
        assert len(note["comments"]) == (1 if expected == "first" else 5)


def test_corrupt_cookie_fails_without_network_or_secret_disclosure(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    offline_xhs: list[str | None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with app.state.session_factory.begin() as db:
        db.get(UserSettings, 1).platform_cookies = {"xiaohongshu": "corrupt-private-value"}
    job_id = submit(client, auth)
    assert app.state.capture_queue.pipeline.run(1, job_id) is None
    response = client.get(f"/api/v1/jobs/{job_id}", headers=auth)
    assert response.json()["status"] == "failed"
    assert "无法解密" in response.json()["last_error"]
    assert "private" not in response.text + caplog.text
    assert offline_xhs == []


def test_public_xhs_note_does_not_require_cookie(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    offline_xhs: list[str | None],
) -> None:
    job_id = submit(client, auth)
    app.state.capture_queue.pipeline.run(1, job_id)
    assert client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()["status"] == "success"
    assert offline_xhs == [None]
