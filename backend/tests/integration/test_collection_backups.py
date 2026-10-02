# SPDX-License-Identifier: AGPL-3.0-or-later
import copy
import io
import zipfile

import pytest
from app.backup_repository import BackupRepository
from app.collection_repository import CollectionRepository
from app.models import Collection, NoteCollection
from app.repositories import IdentityRepository
from app.schemas.backup import Archive
from app.schemas.collection import CollectionCreate
from app.security.credentials import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_backups import export_library, run_job
from test_note_organization import seed_note


def test_collection_archive_restores_memberships_with_new_ids_and_merges_names(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        repo = CollectionRepository(db, 1)
        work = repo.save(CollectionCreate(name="工作", color="blue", icon="briefcase"))
        other = repo.save(CollectionCreate(name="另一空间", color="pink"))
        repo.save(CollectionCreate(name="空空间", color="green"))
        repo.change_notes(work.id, [note_id])
        repo.change_notes(other.id, [note_id])
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
        repo2 = CollectionRepository(db, 2)
        existing = repo2.save(CollectionCreate(name="工作", color="red"))
    foreign_note = seed_note(app, 2)
    with app.state.session_factory.begin() as db:
        CollectionRepository(db, 2).change_notes(existing.id, [foreign_note])
    job, archive = export_library(app, client, auth)
    assert {space["name"] for space in archive["collections"]} == {"工作", "另一空间", "空空间"}
    assert archive["collections"][0]["members"][0]["note_id"] == note_id
    response = client.get(f"/api/v1/backups/{job['id']}/download", headers=auth)
    with zipfile.ZipFile(io.BytesIO(response.content)) as zipped:
        assert "空间：工作、另一空间" in zipped.read(f"markdown/{note_id}.md").decode()
    other_auth = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    imported = client.post("/api/v1/backups/imports", headers=other_auth, json=archive).json()
    for _ in range(2):
        app.state.capture_queue.backups.run(2, imported["id"])
    with app.state.session_factory() as db:
        repo2 = CollectionRepository(db, 2)
        notes, _ = repo2.list_notes(None, 100)
        assert len(notes) == 2
        restored = next(note for note in notes if note.id != foreign_note)
        assert restored.id != note_id
        spaces = {space.name: space for space in repo2.list_collections()}
        assert spaces["工作"].color == "red" and spaces["工作"].note_count == 2
        assert spaces["另一空间"].note_count == 1 and spaces["空空间"].note_count == 0
        memberships = {space.name for space in repo2.list_collections(restored.id)}
        assert memberships == {"工作", "另一空间"}
        links = list(
            db.scalars(select(NoteCollection).where(NoteCollection.note_id == restored.id))
        )
        assert len(links) == 2
        assert (
            next(link for link in links if link.collection_id == spaces["工作"].id)
            .added_at.isoformat()
            .replace("+00:00", "Z")
            == archive["collections"][0]["members"][0]["added_at"]
        )
        assert CollectionRepository(db, 1).list_collections()[0].note_count == 1
        assert BackupRepository(db, 2).backup_job(imported["id"]).status == "success"
    assert (
        client.post("/api/v1/backups/imports", headers=other_auth, json=archive).json()["id"]
        == imported["id"]
    )


@pytest.mark.parametrize("invalid", ["missing_note", "duplicate_member", "duplicate_collection"])
def test_invalid_collection_references_are_atomic(
    app: FastAPI, client: TestClient, auth: dict, invalid: str
) -> None:
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        repo = CollectionRepository(db, 1)
        space = repo.save(CollectionCreate(name="private-space", color="teal"))
        repo.change_notes(space.id, [note_id])
    _, archive = export_library(app, client, auth)
    if invalid == "missing_note":
        archive["collections"][0]["members"][0]["note_id"] = note_id + 1000
    elif invalid == "duplicate_member":
        archive["collections"][0]["members"] *= 2
    else:
        archive["collections"].append(copy.deepcopy(archive["collections"][0]))
    job = run_job(app, client, auth, "/api/v1/backups/imports", json=archive)
    assert job["status"] == "failed" and "private-space" not in str(job)
    with app.state.session_factory() as db:
        assert len(BackupRepository(db, 1).note_ids()) == 1
        assert CollectionRepository(db, 1).list_collections()[0].note_count == 1


def test_empty_collections_and_legacy_archives(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    with app.state.session_factory.begin() as db:
        CollectionRepository(db, 1).save(CollectionCreate(name="空空间", color="yellow"))
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    _, archive = export_library(app, client, auth)
    assert archive["notes"] == [] and archive["collections"][0]["members"] == []
    with app.state.session_factory.begin() as db:
        assert BackupRepository(db, 2).restore(Archive.model_validate(archive)) == 0
    with app.state.session_factory() as db:
        assert CollectionRepository(db, 2).list_collections()[0].name == "空空间"
    del archive["collections"]
    assert Archive.model_validate(archive).collections == []


def test_restore_failure_rolls_back_collections_and_foreign_links_are_not_exported(
    app: FastAPI, client: TestClient, auth: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        repo = CollectionRepository(db, 1)
        space = repo.save(CollectionCreate(name="私有空间", color="teal"))
        repo.change_notes(space.id, [note_id])
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    foreign_note = seed_note(app, 2)
    with app.state.session_factory.begin() as db:
        db.add(NoteCollection(note_id=foreign_note, collection_id=space.id))
    _, archive = export_library(app, client, auth)
    assert [member["note_id"] for member in archive["collections"][0]["members"]] == [note_id]
    original_restore = BackupRepository.restore

    def fail(self: BackupRepository, data: Archive) -> int:
        original_restore(self, data)
        self.db.flush()
        raise RuntimeError("private content")

    monkeypatch.setattr(BackupRepository, "restore", fail)
    other_auth = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    imported = client.post("/api/v1/backups/imports", headers=other_auth, json=archive).json()
    app.state.capture_queue.backups.run(2, imported["id"])
    with app.state.session_factory() as db:
        repo2 = BackupRepository(db, 2)
        assert repo2.backup_job(imported["id"]).status == "retrying"
        assert repo2.note_ids() == [foreign_note]
        assert list(db.scalars(select(Collection).where(Collection.user_id == 2))) == []
