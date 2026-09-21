import json
from typing import Any

import pytest
from app.extractors import xiaohongshu
from app.models import ExtractionCache, UserSettings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.conftest import ACCOUNT
from tests.integration.test_xiaohongshu_capture import HTML, URL


def test_capture_settings_defaults_partial_updates_and_reset(
    client: TestClient, app: FastAPI, auth: dict[str, str]
) -> None:
    assert client.get("/api/v1/settings", headers=auth).json()["capture"] == {"max_comments": 100}
    for value in (0, 1, 100, 7):
        response = client.put(
            "/api/v1/settings", headers=auth, json={"capture": {"max_comments": value}}
        )
        assert response.status_code == 200
        assert response.json()["capture"] == {"max_comments": value}
    for payload in ({}, {"capture": {}}, {"capture": None}, {"llm": {"max_comments": 2}}):
        assert client.put("/api/v1/settings", headers=auth, json=payload).status_code == 200
        assert client.get("/api/v1/settings", headers=auth).json()["capture"]["max_comments"] == 7
    response = client.put(
        "/api/v1/settings", headers=auth, json={"capture": {"max_comments": None}}
    )
    assert response.json()["capture"]["max_comments"] == 100
    assert response.json()["llm"]["max_comments"] == 2
    with app.state.session_factory() as db:
        assert db.get(UserSettings, 1).capture_config == {}


@pytest.mark.parametrize("value", [-1, 101, 1.5, True, "10", [], {}])
def test_invalid_capture_limits_do_not_partially_save_other_settings(
    client: TestClient, auth: dict[str, str], value: Any
) -> None:
    response = client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "capture": {"max_comments": value},
            "llm": {"model": "must-not-save"},
            "platform_cookies": {"xiaohongshu": "session=must-not-save"},
        },
    )
    assert response.status_code == 422
    assert "评论采集上限" in response.json()["error"]["message"]
    assert "must-not-save" not in response.text
    settings = client.get("/api/v1/settings", headers=auth).json()
    assert settings["capture"]["max_comments"] == 100
    assert settings["llm"]["model"] == "qwen-plus"
    assert settings["platform_cookies"]["xiaohongshu"]["cookie_set"] is False


def test_capture_settings_require_auth_and_reject_unknown_fields(
    client: TestClient, auth: dict[str, str]
) -> None:
    assert client.put("/api/v1/settings", json={"capture": {"max_comments": 0}}).status_code == 401
    response = client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comment": 1}})
    assert response.status_code == 422


class RecordingModel:
    def __init__(self) -> None:
        self.inputs: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> str:
        payload = json.loads(kwargs["messages"][1]["content"])
        self.inputs.append(payload)
        return json.dumps(
            {
                "summary_markdown": "完整正文的摘要",
                "key_points": [],
                "comment_scores": [
                    {"index": row["index"], "score": 0.8, "reason": "提供具体信息"}
                    for row in payload["comments"]
                ],
            }
        )


@pytest.fixture
def offline_capture(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str], RecordingModel]:
    requests: list[str] = []

    def fetch(url: str, **kwargs: Any) -> tuple[str, str]:
        requests.append(url)
        return HTML, url

    monkeypatch.setattr(xiaohongshu, "fetch_html", fetch)
    model = RecordingModel()
    app.state.capture_queue.pipeline.llm = model
    return requests, model


def run_capture(
    client: TestClient, app: FastAPI, auth: dict[str, str], *, cached: bool
) -> dict[str, Any]:
    response = client.post("/api/v1/captures", headers=auth, json={"url": URL})
    assert response.status_code == 202
    assert response.json()["cached"] is cached
    job_id = response.json()["job_id"]
    huey = app.state.capture_queue.huey
    huey.execute(huey.dequeue())
    job = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()
    assert job["status"] == "success", job
    assert job["cached"] is cached
    return client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()


def test_capture_limit_precedes_scoring_and_cache_adjusts_without_changing_old_notes(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    offline_capture: tuple[list[str], RecordingModel],
) -> None:
    requests, model = offline_capture
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={"capture": {"max_comments": 3}, "llm": {"api_key": "offline-key", "max_comments": 2}},
    )
    first = run_capture(client, app, auth, cached=False)
    assert len(first["comments"]) == 3
    assert sum(row["ai_score"] is not None for row in first["comments"]) == 2
    assert len(model.inputs[-1]["comments"]) == 2
    for limit, cached, count in [
        (1, True, 1),
        (0, True, 0),
        (3, True, 3),
        (8, False, 8),
        (100, False, 10),
    ]:
        client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": limit}})
        note = run_capture(client, app, auth, cached=cached)
        assert len(note["comments"]) == len(note["content"]["comments"]) == count
        assert note["content"]["comment_capture_limit"] == limit
        assert note["content"]["text"] == first["content"]["text"]
        assert note["status"] == "ready" and note["comment_score_error"] is None
        assert len(model.inputs[-1]["comments"]) == min(count, 2)
    assert len(requests) == 3
    old = client.get(f"/api/v1/notes/{first['id']}", headers=auth).json()
    assert old == first
    with app.state.session_factory() as db:
        cached_content = db.scalar(select(ExtractionCache)).content
        assert len(cached_content["comments"]) == 10
        assert cached_content["raw_html"] == HTML


@pytest.mark.parametrize("initial_limit", [0, 100])
def test_worker_reads_limit_at_execution_and_legacy_cache_is_compatible(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    offline_capture: tuple[list[str], RecordingModel],
    initial_limit: int,
) -> None:
    client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": initial_limit}})
    response = client.post("/api/v1/captures", headers=auth, json={"url": URL})
    client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": 100}})
    huey = app.state.capture_queue.huey
    huey.execute(huey.dequeue())
    job = client.get(f"/api/v1/jobs/{response.json()['job_id']}", headers=auth).json()
    note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()
    assert len(note["comments"]) == 10
    with app.state.session_factory.begin() as db:
        row = db.scalar(select(ExtractionCache))
        row.content = {
            key: value for key, value in row.content.items() if key != "comment_capture_limit"
        }
    client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": 2}})
    assert len(run_capture(client, app, auth, cached=True)["comments"]) == 2
    client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": 100}})
    assert len(run_capture(client, app, auth, cached=True)["comments"]) == 10
    assert len(offline_capture[0]) == 1


def test_disabled_capture_then_enabled_refetches_and_accounts_keep_separate_limits(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    offline_capture: tuple[list[str], RecordingModel],
) -> None:
    app.state.settings.registration_open = True
    second = client.post(
        "/api/v1/auth/register",
        json={**ACCOUNT, "username": "second", "email": "second@example.com"},
    ).json()
    other_auth = {"Authorization": "Bearer " + second["access_token"]}
    client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": 0}})
    disabled = run_capture(client, app, auth, cached=False)
    assert disabled["comments"] == [] and disabled["comment_score_error"] is None
    assert disabled["content"]["comment_capture_limit"] == 0
    assert (
        client.get("/api/v1/settings", headers=other_auth).json()["capture"]["max_comments"] == 100
    )
    assert len(run_capture(client, app, other_auth, cached=False)["comments"]) == 10
    client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": 5}})
    assert len(run_capture(client, app, auth, cached=False)["comments"]) == 5
    assert len(run_capture(client, app, other_auth, cached=True)["comments"]) == 10
    assert len(offline_capture[0]) == 3
    assert client.get(f"/api/v1/notes/{disabled['id']}", headers=other_auth).status_code == 404
