# SPDX-License-Identifier: AGPL-3.0-or-later
from alembic import command
from alembic.config import Config
from app.collection_repository import CollectionRepository
from app.config import BACKEND_ROOT
from app.models import NoteCollection
from app.schemas.collection import CollectionCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from test_note_organization import seed_note


def test_crud_membership_pagination_and_deletion(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    notes = [seed_note(app) for _ in range(3)]
    root = "/api/v1/collections"
    assert client.get(root, headers=auth).json() == {"collections": []}
    created = client.post(root, headers=auth, json={"name": " 工作 ", "color": "blue"})
    assert created.status_code == 201
    space = created.json()
    assert space["name"] == "工作" and space["note_count"] == 0
    path = f"{root}/{space['id']}"
    second = client.post(root, headers=auth, json={"name": "灵感", "color": "green"}).json()
    for _ in range(2):
        assert (
            client.post(path + "/notes", headers=auth, json={"note_ids": notes + notes}).status_code
            == 204
        )
    assert (
        client.post(
            f"{root}/{second['id']}/notes", headers=auth, json={"note_ids": [notes[0]]}
        ).status_code
        == 204
    )
    assert client.get(root, headers=auth).json()["collections"][0]["note_count"] == 3
    page = client.get(path + "/notes?limit=2", headers=auth).json()
    assert [row["id"] for row in page["items"]] == notes[:0:-1]
    rest = client.get(
        path + "/notes", params={"cursor": page["next_cursor"], "limit": 2}, headers=auth
    ).json()
    assert [row["id"] for row in rest["items"]] == notes[:1]
    assert rest["next_cursor"] is None
    assert (
        len(client.get(f"/api/v1/notes?collection_id={space['id']}", headers=auth).json()["items"])
        == 3
    )
    assert (
        len(client.get(root, params={"note_id": notes[0]}, headers=auth).json()["collections"]) == 2
    )
    updated = client.patch(
        path, headers=auth, json={"name": "读书", "color": "pink", "icon": "book"}
    ).json()
    assert updated["name"] == "读书" and updated["icon"] == "book"
    assert client.patch(path, headers=auth, json={"icon": None}).json()["icon"] is None
    for _ in range(2):
        assert (
            client.request(
                "DELETE", path + "/notes", headers=auth, json={"note_ids": [notes[0]]}
            ).status_code
            == 204
        )
    assert client.delete(f"/api/v1/notes/{notes[1]}", headers=auth).status_code == 204
    assert client.get(root, headers=auth).json()["collections"][0]["note_count"] == 1
    assert client.delete(path, headers=auth).status_code == 204
    assert client.get(f"/api/v1/notes/{notes[2]}", headers=auth).status_code == 200
    assert client.get(path + "/notes", headers=auth).status_code == 404
    with app.state.session_factory() as db:
        links = list(db.scalars(select(NoteCollection)))
        assert len(links) == 1 and links[0].collection_id == second["id"]


def test_tenant_isolation_validation_and_atomic_batches(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    root = "/api/v1/collections"
    space = client.post(root, headers=auth, json={"name": "私人", "color": "blue"}).json()
    path = f"{root}/{space['id']}"
    assert (
        client.post(root, headers=auth, json={"name": " 私人 ", "color": "red"}).status_code == 409
    )
    other_space = client.post(root, headers=auth, json={"name": "其他", "color": "red"}).json()
    assert (
        client.patch(f"{root}/{other_space['id']}", headers=auth, json={"name": "私人"}).status_code
        == 409
    )
    app.state.settings.registration_open = True
    user = client.post(
        "/api/v1/auth/register",
        json={"username": "other", "email": "other@example.com", "password": "test-other-password"},
    ).json()
    other = {"Authorization": "Bearer " + user["access_token"]}
    foreign_note = seed_note(app, user["user"]["id"])
    assert client.get(root, headers=other).json()["collections"] == []
    assert (
        client.post(root, headers=other, json={"name": "私人", "color": "blue"}).status_code == 201
    )
    for method, suffix, body in [
        ("PATCH", "", {"name": "泄露"}),
        ("DELETE", "", None),
        ("POST", "/notes", {"note_ids": [foreign_note]}),
        ("DELETE", "/notes", {"note_ids": [foreign_note]}),
        ("GET", "/notes", None),
    ]:
        assert client.request(method, path + suffix, headers=other, json=body).status_code == 404
    assert client.get(root, params={"note_id": note_id}, headers=other).status_code == 404
    assert (
        client.get(f"/api/v1/notes?collection_id={space['id']}", headers=other).json()["items"]
        == []
    )
    for method in ("POST", "DELETE"):
        assert (
            client.request(
                method, path + "/notes", headers=auth, json={"note_ids": [note_id, foreign_note]}
            ).status_code
            == 404
        )
    assert client.get(path + "/notes", headers=auth).json()["items"] == []
    for body in (
        {"name": " "},
        {"color": "black"},
        {"name": None},
        {"color": None},
        {"icon": "unknown"},
        {"user_id": 2},
    ):
        assert client.patch(path, headers=auth, json=body).status_code == 422
    for ids in ([], [True], [0], ["1"], list(range(1, 102))):
        assert client.post(path + "/notes", headers=auth, json={"note_ids": ids}).status_code == 422
    assert client.get(root).status_code == 401


def test_repository_filter_and_migration_roundtrip(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        repo = CollectionRepository(db, 1)
        space = repo.save(CollectionCreate(name="保存", color="teal"))
        repo.change_notes(space.id, [note_id])
        rows, cursor = repo.list_notes(None, 10, collection_id=space.id)
        assert [row.id for row in rows] == [note_id] and cursor is None
        assert repo.list_collections(note_id)[0].note_count == 1
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    for _ in range(2):
        with app.state.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0016_comment_threads")
            assert connection.scalar(text("SELECT count(*) FROM notes")) == 1
            command.upgrade(config, "head")
            command.check(config)
        assert (
            client.get(f"/api/v1/notes/{note_id}", headers=auth).json()["content"]["text"]
            == "整理笔记"
        )
