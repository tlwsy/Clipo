# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest
from app.models import Note
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.integration.test_note_organization import seed_note

HTML = (Path(__file__).parents[1] / "fixtures/site-name.html").read_text()


@pytest.mark.parametrize("stored_name", ["直传站名", None, ""])
def test_list_detail_and_legacy_snapshot_agree(
    app: FastAPI, client: TestClient, auth: dict[str, str], stored_name: str | None
) -> None:
    identifier = seed_note(app)
    with app.state.session_factory.begin() as db:
        note = db.get(Note, identifier)
        assert note is not None
        note.content = {**note.content, "raw_html": HTML}
        if stored_name is not None:
            note.content = {**note.content, "site_name": stored_name}
        else:
            note.content = {key: value for key, value in note.content.items() if key != "site_name"}
    expected = stored_name or "知识 & 阅读"
    item = client.get("/api/v1/notes", headers=auth).json()["items"][0]
    detail = client.get(f"/api/v1/notes/{identifier}", headers=auth).json()
    assert item["site_name"] == detail["source"]["site_name"] == expected
    assert detail["content"]["site_name"] == expected
    assert detail["content"]["raw_html"] is None


def test_browser_payload_name_survives_worker_and_api(
    app: FastAPI, client: TestClient, auth: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/captures",
        headers=auth,
        json={
            "url": "https://example.com/article",
            "payload": {
                "title": "文章",
                "text": "来自浏览器的正文",
                "site_name": "  浏览器  站名  ",
            },
        },
    )
    assert response.status_code == 202
    task = app.state.capture_queue.huey.dequeue()
    app.state.capture_queue.huey.execute(task)
    item = client.get("/api/v1/notes", headers=auth).json()["items"][0]
    assert item["site_name"] == "浏览器 站名"


def test_optional_name_keeps_legacy_capture_idempotency(
    app: FastAPI, client: TestClient, auth: dict[str, str]
) -> None:
    from app.capture_repository import CaptureRepository
    from app.schemas.payload import CapturePayload
    from app.services.captures import fingerprint

    payload = CapturePayload(title="旧请求", text="旧版客户端直传内容").model_dump(
        mode="json", exclude={"site_name"}
    )
    with app.state.session_factory.begin() as db:
        job = CaptureRepository(db, 1).create_job(
            "https://example.com/legacy",
            "legacy-key",
            payload=payload,
            request_hash=fingerprint(payload),
        )
        identifier = job.id
    response = client.post(
        "/api/v1/captures",
        headers={**auth, "Idempotency-Key": "legacy-key"},
        json={"url": "https://example.com/legacy", "payload": payload},
    )
    assert response.status_code == 202
    assert response.json()["job_id"] == identifier
