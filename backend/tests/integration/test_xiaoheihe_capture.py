import pytest
from app.extractors import xiaoheihe
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.integration.test_capture_settings import RecordingModel
from tests.unit.test_xiaoheihe import HTML, SHARE, page


def test_heybox_pipeline_scores_comments_and_respects_cached_limits(
    client: TestClient, app: FastAPI, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = []
    model = RecordingModel()
    app.state.capture_queue.pipeline.llm = model
    monkeypatch.setattr(xiaoheihe, "fetch_html", lambda url, **kwargs: (HTML, url))

    def api_page(self: xiaoheihe.HeyboxClient, identifier: str, number: int, limit: int) -> dict:
        seen.append(self.cookie.value.get_secret_value())
        return page(number)["result"]

    monkeypatch.setattr(xiaoheihe.HeyboxClient, "page", api_page)
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "platform_cookies": {"xiaoheihe": "session=heybox", "xiaohongshu": "session=xhs"},
            "llm": {"api_key": "offline-key", "max_comments": 2},
        },
    )
    for limit, expected_cached in [(10, False), (2, True), (0, True)]:
        client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": limit}})
        response = client.post("/api/v1/captures", headers=auth, json={"url": SHARE})
        job_id = response.json()["job_id"]
        huey = app.state.capture_queue.huey
        huey.execute(huey.dequeue())
        job = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()
        assert job["status"] == "success" and job["cached"] is expected_cached
        note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()
        assert len(note["comments"]) == limit
        assert note["status"] == "ready"
        assert sum(row["is_valuable"] for row in note["comments"]) == min(2, limit)
    assert seen == ["session=heybox", "session=heybox"]
