# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.integration.test_capture_settings import RecordingModel
from tests.unit.test_youtube import URL
from tests.unit.test_youtube import offline_youtube as offline_youtube


def test_youtube_captions_and_comments_flow_to_model_with_cached_limits(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    offline_youtube: list[httpx.Request],
) -> None:
    model = RecordingModel()
    app.state.capture_queue.pipeline.llm = model
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "llm": {"api_key": "offline", "max_comments": 2},
            "platform_cookies": {"xiaohongshu": "a=private", "xiaoheihe": "pkey=private"},
        },
    )
    for limit, cached, comments in [(3, False, 3), (1, True, 1), (0, True, 0), (4, False, 3)]:
        client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": limit}})
        job = client.post("/api/v1/captures", headers=auth, json={"url": URL}).json()
        queue = app.state.capture_queue.huey
        queue.execute(queue.dequeue())
        job = client.get("/api/v1/jobs/" + job["job_id"], headers=auth).json()
        assert job["status"] == "success" and job["cached"] is cached
        note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()
        assert len(note["comments"]) == comments and note["status"] == "ready"
        assert note["content"]["comment_capture_limit"] == limit
        assert "First save the source." in model.inputs[-1]["text"]
        assert len(model.inputs[-1]["comments"]) == min(2, comments)
