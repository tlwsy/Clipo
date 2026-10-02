# SPDX-License-Identifier: AGPL-3.0-or-later
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from app.db.base import utcnow
from app.memory_repository import MemoryGalleryRepository
from app.models import MemoryGalleryDismissal, Note
from app.repositories import IdentityRepository
from app.schemas.backup import Archive
from app.security.credentials import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from test_backups import export_library
from test_note_organization import seed_note

GALLERY = "/api/v1/memory-gallery"


def eligible_note(app: FastAPI, user_id: int = 1) -> int:
    note_id = seed_note(app, user_id)
    with app.state.session_factory.begin() as db:
        note = db.get(Note, note_id)
        note.summary_markdown = "## 回忆\n值得重访的内容"
        note.key_points = ["保留来源", "付诸行动"]
    return note_id


def gallery_ids(client: TestClient, auth: dict) -> set[int]:
    response = client.get(GALLERY, headers=auth)
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["notes"]}


def test_eligibility_never_viewed_recent_view_annotations_and_duration(
    app: FastAPI, client: TestClient, auth: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = utcnow()
    monkeypatch.setattr("app.memory_repository.utcnow", lambda: now)
    summary, recent, boundary = [eligible_note(app) for _ in range(3)]
    plain, annotated, short, long = [seed_note(app) for _ in range(4)]
    with app.state.session_factory.begin() as db:
        db.get(Note, recent).last_viewed_at = now - timedelta(days=7) + timedelta(seconds=1)
        db.get(Note, boundary).last_viewed_at = now - timedelta(days=7)
        db.get(Note, short).reading_duration_seconds = 120
        db.get(Note, long).reading_duration_seconds = 121
        db.get(Note, plain).summary_markdown = "   "
    response = client.post(
        f"/api/v1/notes/{annotated}/annotations",
        headers=auth,
        json={"block_index": 0, "start_offset": 0, "end_offset": 2, "highlight_color": "yellow"},
    )
    assert response.status_code == 201
    assert gallery_ids(client, auth) == {summary, boundary, annotated, long}
    rows = {row["id"]: row for row in client.get(GALLERY, headers=auth).json()["notes"]}
    assert rows[annotated]["annotations_count"] == 1
    assert rows[annotated]["has_summary"] is False
    assert rows[summary]["key_points"] == ["保留来源", "付诸行动"]
    assert rows[summary]["summary_snippet"] == "回忆 值得重访的内容"


def test_view_only_on_explicit_post_and_atomic_capped_increments(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = eligible_note(app)
    path = f"/api/v1/notes/{note_id}"
    before = client.get(path, headers=auth).json()
    assert gallery_ids(client, auth) == {note_id}
    assert (
        client.post(path + "/view", headers=auth, json={"duration_seconds": 0}).status_code == 204
    )
    assert gallery_ids(client, auth) == set()

    def report(_: int) -> None:
        with app.state.session_factory.begin() as db:
            MemoryGalleryRepository(db, 1).record_view(note_id, 30)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(report, range(8)))
    with app.state.session_factory.begin() as db:
        history = MemoryGalleryRepository(db, 1).history(note_id)
        assert history.reading_duration_seconds == 240
        assert history.last_viewed_at is not None
        db.get(Note, note_id).reading_duration_seconds = 2147483646
    report(0)
    with app.state.session_factory() as db:
        assert db.get(Note, note_id).reading_duration_seconds == 2147483647
    assert client.get(path, headers=auth).json()["updated_at"] == before["updated_at"]


def test_dismissal_refresh_expiration_cleanup_and_cascade(
    app: FastAPI, client: TestClient, auth: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = utcnow()
    monkeypatch.setattr("app.memory_repository.utcnow", lambda: now)
    monkeypatch.setattr("app.tasks.memory.utcnow", lambda: now)
    note_id, expired_id = eligible_note(app), eligible_note(app)
    for _ in range(2):
        assert (
            client.post(GALLERY + "/dismiss", headers=auth, json={"note_id": note_id}).status_code
            == 204
        )
    with app.state.session_factory.begin() as db:
        MemoryGalleryRepository(db, 1).dismiss(expired_id, now - timedelta(days=30))
        assert len(list(db.scalars(select(MemoryGalleryDismissal)))) == 2
    assert gallery_ids(client, auth) == {expired_id}
    app.state.capture_queue.memory.cleanup()
    app.state.capture_queue.memory.cleanup()
    with app.state.session_factory() as db:
        assert [row.note_id for row in db.scalars(select(MemoryGalleryDismissal))] == [note_id]
    assert client.delete(f"/api/v1/notes/{note_id}", headers=auth).status_code == 204
    with app.state.session_factory() as db:
        assert db.scalar(select(MemoryGalleryDismissal)) is None


def test_memory_is_user_scoped_and_requires_authentication(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = eligible_note(app)
    with app.state.session_factory.begin() as db:
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    other_id = eligible_note(app, 2)
    other = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    assert gallery_ids(client, other) == {other_id}
    assert gallery_ids(client, auth) == {note_id}
    for path, body in [
        (f"/notes/{note_id}/view", {"duration_seconds": 100}),
        ("/memory-gallery/dismiss", {"note_id": note_id}),
    ]:
        assert client.post("/api/v1" + path, json=body, headers=other).status_code == 404
        assert client.post("/api/v1" + path, json=body).status_code == 401
    assert client.get(GALLERY).status_code == 401
    assert gallery_ids(client, auth) == {note_id}


@pytest.mark.parametrize("duration", [-1, 301, 1.2, True, "20", None])
def test_invalid_duration(client: TestClient, auth: dict, duration: object) -> None:
    assert (
        client.post(
            "/api/v1/notes/1/view", headers=auth, json={"duration_seconds": duration}
        ).status_code
        == 422
    )


def test_count_validation_and_bounded_results(app: FastAPI, client: TestClient, auth: dict) -> None:
    for _ in range(18):
        eligible_note(app)
    for count in (10, 15):
        rows = client.get(GALLERY, headers=auth, params={"count": count}).json()["notes"]
        assert len(rows) == len({row["id"] for row in rows}) == count
    for count in (0, 9, 16, 10000, "bad"):
        assert client.get(GALLERY, headers=auth, params={"count": count}).status_code == 422
    assert (
        client.post(GALLERY + "/dismiss", headers=auth, json={"note_id": True}).status_code == 422
    )


def test_migration_preserves_existing_notes_and_search(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = eligible_note(app)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0019_semantic_search")
        assert "memory_gallery_dismissals" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        assert connection.scalar(text("SELECT reading_duration_seconds FROM notes")) == 0
    assert gallery_ids(client, auth) == {note_id}
    assert client.get("/api/v1/notes?q=知识", headers=auth).json()["items"][0]["id"] == note_id


def test_backup_preserves_private_history_and_older_archives_default_to_empty(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    from app.backup_repository import BackupRepository

    note_id = eligible_note(app)
    client.post(f"/api/v1/notes/{note_id}/view", headers=auth, json={"duration_seconds": 123})
    client.post(GALLERY + "/dismiss", headers=auth, json={"note_id": note_id})
    _, archive = export_library(app, client, auth)
    saved = archive["notes"][0]
    assert saved["reading_duration_seconds"] == 123
    assert saved["last_viewed_at"] and saved["memory_dismissed_at"]
    with app.state.session_factory.begin() as db:
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
        BackupRepository(db, 2).restore(Archive.model_validate(archive))
        restored_id = BackupRepository(db, 2).note_ids()[0]
        restored = MemoryGalleryRepository(db, 2).history(restored_id).model_dump(mode="json")
        assert all(restored[key] == saved[key] for key in restored)
        assert restored_id != note_id
        assert MemoryGalleryRepository(db, 2).gallery(15).notes == []
    for key in restored:
        saved.pop(key)
    assert Archive.model_validate(archive).notes[0].reading_duration_seconds == 0
    assert Archive.model_validate(archive).notes[0].last_viewed_at is None
    detail = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
    assert not set(restored).intersection(detail)
