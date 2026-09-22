# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from app.db.base import utcnow
from app.models import CaptureJob, CaptureUpload, CaptureUploadChunk, ExtractionCache
from app.schemas.payload import CHUNK_BYTES, DIRECT_BYTES
from app.tasks.capture import CaptureQueue
from sqlalchemy import func, select

URL = "https://www.xiaohongshu.com/explore/browser123"
PAYLOAD = {
    "title": "浏览器正文",
    "text": "从已登录页面读取的完整正文",
    "selection": "选中的一段文字",
    "tags": ["浏览器"],
    "comments": [{"author": "甲", "content": "具体补充的参数信息", "likes": 8}],
}


def post(client, auth, payload=None, key="direct") -> dict:
    response = client.post(
        "/api/v1/captures",
        headers={**auth, "Idempotency-Key": key},
        json={"url": URL, "payload": payload or PAYLOAD},
    )
    assert response.status_code == 202, response.text
    return response.json()


def upload(client, auth, data: bytes, key="upload", digest=None) -> dict:
    response = client.post(
        "/api/v1/captures/uploads",
        headers={**auth, "Idempotency-Key": key},
        json={
            "url": URL,
            "total_bytes": len(data),
            "sha256": digest or hashlib.sha256(data).hexdigest(),
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def send_chunks(client, auth, job: dict, data: bytes) -> None:
    for index, offset in enumerate(range(0, len(data), CHUNK_BYTES)):
        response = client.put(
            f"/api/v1/captures/{job['job_id']}/chunks/{index}",
            headers=auth,
            content=data[offset : offset + CHUNK_BYTES],
        )
        assert response.status_code == 204, response.text


def test_payload_bypasses_network_and_cache_and_preserves_selection_tags(
    client, app, auth, monkeypatch
) -> None:
    from app.extractors.registry import ExtractorRegistry

    def forbidden(*args, **kwargs):
        raise AssertionError("DOM content must not fetch target")

    monkeypatch.setattr(ExtractorRegistry, "get", forbidden)
    job = post(client, auth)
    replacement = CaptureQueue(app.state.session_factory, app.state.settings)
    replacement.pipeline.run(1, job["job_id"])
    job = client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth).json()
    assert job["status"] == "success" and job["cached"] is False
    note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()
    assert note["content"]["text"] == PAYLOAD["text"]
    assert note["content"]["selection"] == PAYLOAD["selection"]
    assert note["source"]["platform"] == "xiaohongshu"
    assert note["comments"][0]["likes"] == 8
    assert note["tags"][0]["name"] == "浏览器"
    assert note["status"] == "original_only"
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ExtractionCache)) == 0
    assert post(client, auth)["job_id"] == job["job_id"]
    conflict = client.post(
        "/api/v1/captures",
        headers={**auth, "Idempotency-Key": "direct"},
        json={"url": URL, "payload": {**PAYLOAD, "text": "different"}},
    )
    assert conflict.status_code == 409


def test_comments_use_execution_time_account_limit(client, app, auth) -> None:
    job = post(client, auth)
    client.put("/api/v1/settings", headers=auth, json={"capture": {"max_comments": 0}})
    app.state.capture_queue.pipeline.run(1, job["job_id"])
    job = client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth).json()
    note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()
    assert note["comments"] == [] and note["content"]["comments"] == []


@pytest.mark.parametrize(
    "change",
    [
        {"text": " "},
        {"raw_html": "secret"},
        {"images": ["javascript:alert(1)"]},
        {"author_url": "http://127.0.0.1"},
        {"comments": [{"content": "secret", "likes": -1}]},
    ],
)
def test_invalid_payload_is_rejected_without_echo(client, auth, change) -> None:
    response = client.post(
        "/api/v1/captures", headers=auth, json={"url": URL, "payload": {**PAYLOAD, **change}}
    )
    assert response.status_code == 422
    assert "secret" not in response.text


def test_chunk_upload_survives_restart_is_idempotent_and_never_runs_early(
    client, app, auth
) -> None:
    data = json.dumps({**PAYLOAD, "text": "内容" * 120000}, ensure_ascii=False).encode()
    job = upload(client, auth, data)
    assert job["status"] == "uploading"
    replacement = CaptureQueue(app.state.session_factory, app.state.settings)
    replacement.recover()
    assert replacement.huey.dequeue() is None
    replacement.pipeline.run(1, job["job_id"])
    assert client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth).json()["attempts"] == 0
    endpoint = f"/api/v1/captures/{job['job_id']}/complete"
    assert client.post(endpoint, headers=auth).status_code == 409
    send_chunks(client, auth, job, data)
    send_chunks(client, auth, job, data)  # Retry after losing acknowledgements.
    assert upload(client, auth, data)["job_id"] == job["job_id"]
    assert client.post(endpoint, headers=auth).json()["status"] == "queued"
    assert client.post(endpoint, headers=auth).status_code == 202
    replacement.recover()
    replacement.pipeline.run(1, job["job_id"])
    result = client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth).json()
    assert result["status"] == "success"
    assert (
        client.get(f"/api/v1/notes/{result['note_id']}", headers=auth).json()["content"]["text"]
        == "内容" * 120000
    )
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CaptureUploadChunk)) == 0


def test_chunk_limits_hash_isolation_expiry_and_retry(client, app, auth) -> None:
    data = json.dumps(PAYLOAD).encode()
    job = upload(client, auth, data, digest="0" * 64)
    base = f"/api/v1/captures/{job['job_id']}"
    app.state.settings.registration_open = True
    other = client.post(
        "/api/v1/auth/register",
        json={"username": "other", "email": "other@example.com", "password": "other-long-password"},
    ).json()
    foreign = {"Authorization": "Bearer " + other["access_token"]}
    assert client.put(base + "/chunks/0", headers=foreign, content=data).status_code == 404
    assert client.post(base + "/complete", headers=foreign).status_code == 404
    assert client.put(base + "/chunks/1", headers=auth, content=data).status_code == 422
    send_chunks(client, auth, job, data)
    assert client.put(base + "/chunks/0", headers=auth, content=b"x" * len(data)).status_code == 409
    assert client.post(base + "/complete", headers=auth).status_code == 422
    with app.state.session_factory.begin() as db:
        db.get(CaptureUpload, job["job_id"]).expires_at = utcnow() - timedelta(seconds=1)
    assert client.post(base + "/complete", headers=auth).status_code == 410
    app.state.capture_queue.recover()
    assert client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth).json()["status"] == "failed"
    assert client.post(f"/api/v1/jobs/{job['job_id']}/retry", headers=auth).status_code == 409
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CaptureUpload)) == 0


def test_request_body_limits_and_invalid_uploaded_json(client, auth) -> None:
    assert (
        client.post("/api/v1/captures", headers=auth, content=b"x" * (DIRECT_BYTES + 1)).status_code
        == 413
    )
    data = b'{"text": "missing title"}'
    job = upload(client, auth, data)
    assert (
        client.put(
            f"/api/v1/captures/{job['job_id']}/chunks/0",
            headers=auth,
            content=b"x" * (CHUNK_BYTES + 1),
        ).status_code
        == 413
    )
    send_chunks(client, auth, job, data)
    assert (
        client.post(f"/api/v1/captures/{job['job_id']}/complete", headers=auth).status_code == 422
    )


def test_concurrent_upload_start(client, auth) -> None:
    data = json.dumps(PAYLOAD).encode()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(client, auth, data), range(2)))
    assert results[0]["job_id"] == results[1]["job_id"]


def test_payload_migration_roundtrip_preserves_old_job_and_account(client, app, auth) -> None:
    job = post(client, auth)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0009_shortcut_pairings")
        command.upgrade(config, "head")
        command.check(config)
    with app.state.session_factory() as db:
        assert db.get(CaptureJob, job["job_id"]).url == URL
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200


def test_upload_start_rolls_back_job_if_descriptor_fails(client, app, auth, monkeypatch) -> None:
    from app.upload_repository import UploadRepository
    from sqlalchemy.exc import SQLAlchemyError

    def fail(*args, **kwargs):
        raise SQLAlchemyError("temporary database failure")

    monkeypatch.setattr(UploadRepository, "start_upload", fail)
    response = client.post(
        "/api/v1/captures/uploads",
        headers=auth,
        json={
            "url": URL,
            "total_bytes": 100,
            "sha256": "0" * 64,
        },
    )
    assert response.status_code == 503
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CaptureJob)) == 0
