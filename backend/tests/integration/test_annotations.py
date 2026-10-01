# SPDX-License-Identifier: AGPL-3.0-or-later
import copy
import io
import zipfile

import pytest
from alembic import command
from alembic.config import Config
from app.annotation_repository import AnnotationRepository
from app.backup_repository import BackupRepository
from app.config import BACKEND_ROOT
from app.models import Annotation
from app.repositories import IdentityRepository
from app.schemas.annotation import AnnotationCreate
from app.schemas.reading import ReadingStylePatch
from app.security.credentials import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from test_backups import export_library, run_job
from test_note_organization import seed_note

BODY = {
    "block_index": 0,
    "start_offset": 0,
    "end_offset": 2,
    "highlight_color": "yellow",
    "selected_text": "整理",
}
PREFERENCES = "/api/v1/user/reading-preferences"


def test_annotation_crud_overlaps_and_private_shares(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    path = f"/api/v1/notes/{note_id}"
    assert client.get(path + "/annotations", headers=auth).json() == {"annotations": []}
    response = client.post(path + "/annotations", headers=auth, json=BODY)
    assert response.status_code == 201, response.text
    annotation = response.json()
    endpoint = f"/api/v1/annotations/{annotation['id']}"
    assert annotation["selected_text"] == "整理"
    second = client.post(
        path + "/annotations",
        headers=auth,
        json={
            **BODY,
            "highlight_color": None,
            "note_text": "私人批注",
            "end_offset": 4,
            "selected_text": "整理笔记",
        },
    )
    assert second.status_code == 201
    note = client.get(path, headers=auth).json()
    assert len(note["annotations"]) == 2
    assert note["reading_preferences"]["theme"] == "comfortable"
    assert (
        client.patch(
            endpoint, headers=auth, json={"note_text": "新的笔记", "highlight_color": "green"}
        ).json()["highlight_color"]
        == "green"
    )
    assert (
        client.patch(endpoint, headers=auth, json={"highlight_color": None}).json()["note_text"]
        == "新的笔记"
    )
    assert client.patch(endpoint, headers=auth, json={"note_text": " "}).status_code == 422
    assert client.patch(endpoint, headers=auth, json={"start_offset": 1}).status_code == 422
    share = client.post(path + "/shares", headers=auth, json={}).json()
    public = client.post("/api/v1/public/notes/read", json={"token": share["token"]})
    assert public.status_code == 200
    assert "私人批注" not in public.text and "annotations" not in public.json()
    assert client.delete(endpoint, headers=auth).status_code == 204
    assert client.delete(endpoint, headers=auth).status_code == 404
    assert client.delete(path, headers=auth).status_code == 204
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Annotation)) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"block_index": 1},
        {"block_index": -1},
        {"start_offset": -1},
        {"start_offset": True},
        {"end_offset": 5},
        {"end_offset": 0},
        {"selected_text": "不匹配"},
        {"highlight_color": "red"},
        {"highlight_color": None},
        {"user_id": 2},
        {"note_text": "x" * 5001},
        {"note_text": "private\x00value"},
    ],
)
def test_invalid_annotations_are_rejected(
    app: FastAPI, client: TestClient, auth: dict, change: dict
) -> None:
    note_id = seed_note(app)
    response = client.post(
        f"/api/v1/notes/{note_id}/annotations", headers=auth, json={**BODY, **change}
    )
    assert response.status_code == 422, response.text
    assert "private" not in response.text


def test_owner_scoping_and_preferences(app: FastAPI, client: TestClient, auth: dict) -> None:
    note_id = seed_note(app)
    path = f"/api/v1/notes/{note_id}"
    annotation = client.post(path + "/annotations", headers=auth, json=BODY).json()
    with app.state.session_factory.begin() as db:
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    other = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    for method, url, body in (
        ("GET", path + "/annotations", None),
        ("POST", path + "/annotations", BODY),
        ("PATCH", f"/api/v1/annotations/{annotation['id']}", {"note_text": "bad"}),
        ("DELETE", f"/api/v1/annotations/{annotation['id']}", None),
        ("PATCH", path + "/display", {"font_size": 22}),
        ("DELETE", path + "/display", None),
    ):
        assert client.request(method, url, headers=other, json=body).status_code == 404
        assert client.request(method, url, json=body).status_code == 401
    assert (
        client.patch(PREFERENCES, headers=auth, json={"theme": "focus", "font_size": 24}).json()[
            "font_size"
        ]
        == 24
    )
    assert client.get(PREFERENCES, headers=other).json()["theme"] == "comfortable"
    assert (
        client.patch(PREFERENCES, headers=auth, json={"font_size": None}).json()["font_size"] == 20
    )
    assert client.patch(path + "/display", headers=auth, json={"font_size": 22}).json() == {
        "font_size": 22
    }
    assert client.patch(path + "/display", headers=auth, json={"text_align": "justify"}).json() == {
        "font_size": 22,
        "text_align": "justify",
    }
    assert client.patch(path + "/display", headers=auth, json={"theme": "compact"}).json() == {
        "theme": "compact"
    }
    assert client.get(path, headers=auth).json()["reading_preferences"]["theme"] == "focus"
    assert client.delete(path + "/display", headers=auth).status_code == 204
    assert not any(client.get(path, headers=auth).json()["display_overrides"].values())
    for body in (
        {"background_color": "red"},
        {"content_width": 10000},
        {"font_size": True},
        {"theme": "bad"},
        {"unknown": 1},
    ):
        assert client.patch(PREFERENCES, headers=auth, json=body).status_code == 422
    # Corrupt legacy ownership must never become visible via the note join.
    with app.state.session_factory.begin() as db:
        db.add(Annotation(user_id=2, note_id=note_id, **{**BODY, "selected_text": "整理"}))
    assert len(client.get(path + "/annotations", headers=auth).json()["annotations"]) == 1
    assert client.get(PREFERENCES).status_code == 401


def test_annotations_backup_and_legacy_restore(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        repo = AnnotationRepository(db, 1)
        repo.create_annotation(note_id, AnnotationCreate(**BODY, note_text="保留批注"))
        repo.save_display(note_id, ReadingStylePatch(font_size=22))
        repo.save_preferences(ReadingStylePatch(theme="focus"))
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    job, archive = export_library(app, client, auth)
    with zipfile.ZipFile(
        io.BytesIO(client.get(f"/api/v1/backups/{job['id']}/download", headers=auth).content)
    ) as zipped:
        assert "保留批注" in zipped.read(f"markdown/{note_id}.md").decode()
    other = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    imported = client.post("/api/v1/backups/imports", headers=other, json=archive).json()
    for _ in range(2):
        app.state.capture_queue.backups.run(2, imported["id"])
    notes = client.get("/api/v1/notes", headers=other).json()["items"]
    assert len(notes) == 1
    restored = client.get(f"/api/v1/notes/{notes[0]['id']}", headers=other).json()
    assert restored["id"] != note_id
    assert restored["annotations"][0]["id"] != archive["notes"][0]["annotations"][0]["id"]
    assert restored["annotations"][0]["note_text"] == "保留批注"
    assert (
        restored["annotations"][0]["created_at"]
        == archive["notes"][0]["annotations"][0]["created_at"]
    )
    assert restored["display_overrides"]["font_size"] == 22
    assert restored["reading_preferences"]["theme"] == "focus"
    # Old archives have no reading fields and do not overwrite a configured destination.
    archive.pop("reading_preferences")
    for key in ("annotations", "reading_preferences", "display_overrides"):
        archive["notes"][0].pop(key)
    from app.schemas.backup import Archive

    with app.state.session_factory.begin() as db:
        BackupRepository(db, 2).restore(Archive.model_validate(archive))
        assert AnnotationRepository(db, 2).reading_preferences().theme == "focus"


@pytest.mark.parametrize("invalid", ["range", "quote", "duplicate", "style"])
def test_invalid_archive_annotations_fail_atomically(
    app: FastAPI, client: TestClient, auth: dict, invalid: str
) -> None:
    note_id = seed_note(app)
    client.post(f"/api/v1/notes/{note_id}/annotations", headers=auth, json=BODY)
    _, archive = export_library(app, client, auth)
    changed = copy.deepcopy(archive)
    if invalid == "range":
        changed["notes"][0]["annotations"][0]["end_offset"] = 99
    elif invalid == "quote":
        changed["notes"][0]["annotations"][0]["selected_text"] = "private-content"
    elif invalid == "duplicate":
        changed["notes"][0]["annotations"] *= 2
    else:
        changed["notes"][0]["display_overrides"]["font_size"] = 99
    job = run_job(app, client, auth, "/api/v1/backups/imports", json=changed)
    assert job["status"] == "failed" and "private-content" not in str(job)
    assert len(client.get("/api/v1/notes", headers=auth).json()["items"]) == 1


def test_annotations_migration_roundtrip(app: FastAPI, client: TestClient, auth: dict) -> None:
    note_id = seed_note(app)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    for _ in range(2):
        client.post(f"/api/v1/notes/{note_id}/annotations", headers=auth, json=BODY)
        with app.state.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0017_collections")
            assert connection.scalar(text("SELECT count(*) FROM notes")) == 1
            command.upgrade(config, "head")
            command.check(config)
        result = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
        assert result["content"]["text"] == "整理笔记" and result["annotations"] == []
        assert result["reading_preferences"]["font_size"] == 18
