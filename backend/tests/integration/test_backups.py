import io
import json
import zipfile
from datetime import timedelta

import pytest
from app.backup_repository import BackupRepository
from app.db.base import utcnow
from app.models import Comment, Note, Tag
from app.repositories import IdentityRepository
from app.schemas.backup import Archive
from app.security.credentials import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.integration.test_note_organization import seed_note


def run_job(app: FastAPI, client: TestClient, auth: dict, path: str, **kwargs: object) -> dict:
    response = client.post(path, headers=auth, **kwargs)
    assert response.status_code == 202, response.text
    job = response.json()
    app.state.capture_queue.backups.run(1, job["id"])
    return next(
        row for row in client.get("/api/v1/backups", headers=auth).json() if row["id"] == job["id"]
    )


def export_library(app: FastAPI, client: TestClient, auth: dict) -> tuple[dict, dict]:
    job = run_job(app, client, auth, "/api/v1/backups/exports", json={"request_key": "test"})
    assert job["status"] == "success", job
    response = client.get(f"/api/v1/backups/{job['id']}/download", headers=auth)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        data = json.loads(archive.read("library.json"))
        for note in data["notes"]:
            assert note["content"]["text"] in archive.read(f"markdown/{note['id']}.md").decode()
        return job, data


def test_export_import_roundtrip_preserves_library_and_is_idempotent(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    client.post(f"/api/v1/notes/{note_id}/tags", headers=auth, json={"name": "中文标签"})
    with app.state.session_factory.begin() as db:
        note = db.get(Note, note_id)
        note.content = {
            **note.content,
            "raw_html": "<p>原始快照</p>",
            "images": ["https://example.com/image.jpg"],
            "selection": "摘录",
        }
        note.summary_markdown, note.is_favorite = "**摘要**", True
        db.add(
            Comment(
                note_id=note_id,
                content="有价值的评论",
                author="作者",
                likes=9,
                replies=2,
                position=0,
                ai_score=0.9,
                ai_reason="包含数据",
                is_valuable=True,
            )
        )
        db.add(Tag(user_id=1, name="未使用标签"))
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    job, archive = export_library(app, client, auth)
    assert set(archive) == {"format", "version", "exported_at", "tags", "notes"}
    assert archive["notes"][0]["content"]["raw_html"] == "<p>原始快照</p>"
    other_auth = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    assert (
        client.get(f"/api/v1/backups/{job['id']}/download", headers=other_auth).status_code == 404
    )
    assert client.get("/api/v1/backups", headers=other_auth).json() == []
    imported = client.post("/api/v1/backups/imports", headers=other_auth, json=archive).json()
    for _ in range(2):
        app.state.capture_queue.backups.run(2, imported["id"])
    with app.state.session_factory() as db:
        repository = BackupRepository(db, 2)
        assert repository.backup_job(imported["id"]).status == "success"
        ids = repository.note_ids()
        assert len(ids) == 1 and ids[0] != note_id
        restored = repository.note(ids[0])
        original = db.get(Note, note_id)
        for field in (
            "title",
            "url",
            "content",
            "summary_markdown",
            "key_points",
            "suggested_tags",
            "status",
            "is_favorite",
            "summary_error",
            "comment_score_error",
            "created_at",
            "updated_at",
        ):
            assert getattr(restored, field) == getattr(original, field)
        assert {tag.name for tag in repository.list_tags()} == {"中文标签", "未使用标签"}
        comment = repository.comments(ids[0])[0]
        assert comment.ai_score == 0.9 and comment.is_valuable and comment.likes == 9
    again = client.post("/api/v1/backups/imports", headers=other_auth, json=archive).json()
    assert again["id"] == imported["id"]
    assert client.get("/api/v1/notes?q=整理", headers=other_auth).json()["items"][0]["id"] == ids[0]


def test_invalid_import_is_atomic_and_errors_hide_content(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    seed_note(app)
    _, archive = export_library(app, client, auth)
    archive["notes"].append({"secret": "DO-NOT-ECHO"})
    job = run_job(app, client, auth, "/api/v1/backups/imports", json=archive)
    assert job["status"] == "failed"
    assert "DO-NOT-ECHO" not in json.dumps(job)
    assert len(client.get("/api/v1/notes", headers=auth).json()["items"]) == 1
    assert client.get(f"/api/v1/backups/{job['id']}/download", headers=auth).status_code == 409


def test_export_claim_recovery_fencing_and_failed_retry(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    response = client.post(
        "/api/v1/backups/exports", headers=auth, json={"request_key": "recovery"}
    )
    job_id = response.json()["id"]
    assert (
        client.post(
            "/api/v1/backups/exports", headers=auth, json={"request_key": "recovery"}
        ).json()["id"]
        == job_id
    )
    with app.state.session_factory.begin() as db:
        repository = BackupRepository(db, 1)
        assert repository.claim_backup(job_id, "stale") is not None
        assert repository.claim_backup(job_id, "duplicate") is None
        repository.backup_job(job_id).lease_expires_at = utcnow() - timedelta(seconds=1)
    app.state.capture_queue.backups.run(1, job_id)
    with app.state.session_factory.begin() as db:
        repository = BackupRepository(db, 1)
        assert repository.backup_job(job_id).status == "success"
        assert not repository.fence_backup(job_id, "stale", status="failed")
        repository.backup_job(job_id).status = "failed"
    assert client.post(f"/api/v1/backups/{job_id}/retry", headers=auth).status_code == 202
    app.state.capture_queue.backups.run(1, job_id)
    assert client.get("/api/v1/backups", headers=auth).json()[0]["status"] == "success"


def test_import_failure_rolls_back_all_notes(
    app: FastAPI, client: TestClient, auth: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_note(app)
    _, archive = export_library(app, client, auth)
    original_restore = BackupRepository.restore

    def fail_after_restore(self: BackupRepository, data: Archive) -> int:
        original_restore(self, data)
        self.db.flush()
        raise RuntimeError("sensitive body")

    monkeypatch.setattr(BackupRepository, "restore", fail_after_restore)
    job = run_job(app, client, auth, "/api/v1/backups/imports", json=archive)
    assert job["status"] == "retrying"
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(Note)))) == 1


def test_backups_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/backups").status_code == 401
    assert client.post("/api/v1/backups/imports", content=b"private").status_code == 401
