# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import json
import zipfile

from app.capture_repository import CaptureRepository
from app.content import blocks_text
from app.extractors.base import CapturedContent
from app.extractors.xiaoheihe import parse_heybox
from app.models import Note
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.integration.test_backups import run_job
from tests.integration.test_note_organization import seed_note
from tests.integration.test_sharing import issue
from tests.unit.test_heybox_content import HTML


def rich() -> CapturedContent:
    return parse_heybox(
        {"link": {"title": "结构回归", "text": json.dumps([{"type": "html", "text": HTML}])}},
        "https://www.xiaoheihe.cn/app/bbs/link/123",
        "<html></html>",
        0,
    )


def test_ordered_content_survives_notes_share_archive_and_restore(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    content = rich()
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        note = db.get(Note, note_id)
        note.content = content.model_dump(mode="json")
    detail = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
    assert detail["content"]["blocks"] == content.model_dump()["blocks"]
    link = issue(client, auth, note_id)
    public = client.post("/api/v1/public/notes/read", json={"token": link["token"]}).json()
    assert public["blocks"] == detail["content"]["blocks"]
    assert "raw_html" not in public
    job = run_job(app, client, auth, "/api/v1/backups/exports", json={"request_key": "rich"})
    assert job["status"] == "success"
    response = client.get(f"/api/v1/backups/{job['id']}/download", headers=auth)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        data = json.loads(archive.read("library.json"))
        markdown = archive.read(f"markdown/{note_id}.md").decode()
    assert "## 第一章" in markdown and "![步骤一：选择文件]" in markdown
    assert "展开补充" in markdown and "折叠正文" in markdown
    assert data["notes"][0]["content"]["blocks"] == detail["content"]["blocks"]
    client.delete(f"/api/v1/notes/{note_id}", headers=auth)
    restored = run_job(app, client, auth, "/api/v1/backups/imports", json=data)
    assert restored["status"] == "success"
    restored_id = client.get("/api/v1/notes", headers=auth).json()["items"][0]["id"]
    restored_note = client.get(f"/api/v1/notes/{restored_id}", headers=auth).json()
    assert restored_note["content"]["blocks"] == detail["content"]["blocks"]
    assert client.get("/api/v1/notes?q=折叠正文", headers=auth).json()["items"]


def test_old_heybox_cache_is_invalidated_and_new_structure_is_isolated(
    app: FastAPI, auth: dict
) -> None:
    content = rich()
    with app.state.session_factory.begin() as db:
        repo = CaptureRepository(db, 1)
        repo.put_cache(content.url, content.model_copy(update={"extractor_version": 1}), 100)
        assert repo.cache(content.url, max_comments=0) is None
        repo.put_cache(content.url, content, 100)
        assert repo.cache(content.url, max_comments=0).blocks == content.blocks
        assert CaptureRepository(db, 99).cache(content.url, max_comments=0) is None


def test_direct_capture_derives_search_text_and_rejects_unsafe_blocks(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    content = rich()
    payload = {"title": "直传结构", "text": "兼容摘要", "blocks": content.model_dump()["blocks"]}
    response = client.post(
        "/api/v1/captures", headers=auth, json={"url": content.url, "payload": payload}
    )
    assert response.status_code == 202
    huey = app.state.capture_queue.huey
    huey.execute(huey.dequeue())
    job = client.get(f"/api/v1/jobs/{response.json()['job_id']}", headers=auth).json()
    assert job["status"] == "success"
    note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()
    assert note["content"]["text"] == blocks_text(content.blocks)
    payload["blocks"] = [{"type": "image", "url": "http://127.0.0.1/private"}]
    invalid = client.post(
        "/api/v1/captures", headers=auth, json={"url": content.url, "payload": payload}
    )
    assert invalid.status_code == 422 and "127.0.0.1" not in invalid.text
