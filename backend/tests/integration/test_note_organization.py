from app.extractors.base import CapturedContent
from app.llm.orchestrator import SummaryResult
from app.models import NoteTag, Tag
from app.note_repository import NoteRepository
from app.schemas.capture import TagRequest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select


def seed_note(app: FastAPI, user_id: int = 1) -> int:
    with app.state.session_factory.begin() as db:
        repository = NoteRepository(db, user_id)
        job = repository.create_job("https://example.com/note", None)
        repository.claim(job.id, "test-execution")
        repository.finish(
            job.id,
            "test-execution",
            CapturedContent(url=job.url, title="知识管理", text="整理笔记"),
            SummaryResult(None, "未配置模型"),
            False,
        )
        return job.note_id


def test_tags_favorites_filter_and_idempotent_removal(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    second_id = seed_note(app)
    path = f"/api/v1/notes/{note_id}"
    tag = client.post(path + "/tags", headers=auth, json={"name": "  工作   灵感  "}).json()
    assert tag["name"] == "工作 灵感"
    assert client.post(path + "/tags", headers=auth, json={"name": "工作 灵感"}).json() == tag
    assert client.get("/api/v1/tags", headers=auth).json() == [tag]
    result = client.patch(path, headers=auth, json={"is_favorite": True})
    assert result.status_code == 200 and result.json()["is_favorite"]
    assert result.json()["tags"] == [tag]
    filtered = client.get(
        "/api/v1/notes", headers=auth, params={"tag_id": tag["id"], "favorite": True, "limit": 1}
    ).json()
    assert [row["id"] for row in filtered["items"]] == [note_id]
    assert filtered["next_cursor"] is None
    assert [
        row["id"]
        for row in client.get("/api/v1/notes?favorite=false", headers=auth).json()["items"]
    ] == [second_id]
    for _ in range(2):
        assert client.delete(path + f"/tags/{tag['id']}", headers=auth).status_code == 204
    assert client.get(path, headers=auth).json()["tags"] == []
    assert client.delete(f"/api/v1/tags/{tag['id']}", headers=auth).status_code == 204
    assert client.get(path, headers=auth).status_code == 200


def test_organization_is_scoped_and_input_is_validated(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    tag = client.post(
        f"/api/v1/notes/{note_id}/tags", headers=auth, json={"name": "私有标签"}
    ).json()
    app.state.settings.registration_open = True
    session = client.post(
        "/api/v1/auth/register",
        json={"username": "other", "email": "other@example.com", "password": "other-test-password"},
    ).json()
    other = {"Authorization": "Bearer " + session["access_token"]}
    assert client.get("/api/v1/tags", headers=other).json() == []
    for method, path, body in [
        ("PATCH", f"/notes/{note_id}", {"is_favorite": True}),
        ("POST", f"/notes/{note_id}/tags", {"name": "test"}),
        ("DELETE", f"/notes/{note_id}/tags/{tag['id']}", None),
        ("DELETE", f"/tags/{tag['id']}", None),
    ]:
        assert client.request(method, "/api/v1" + path, json=body, headers=other).status_code == 404
    assert client.get(f"/api/v1/notes?tag_id={tag['id']}", headers=other).json()["items"] == []
    for name in ("", "  \n ", "x" * 51):
        assert (
            client.post(
                f"/api/v1/notes/{note_id}/tags", headers=auth, json={"name": name}
            ).status_code
            == 422
        )
    assert (
        client.patch(
            f"/api/v1/notes/{note_id}", headers=auth, json={"is_favorite": "true"}
        ).status_code
        == 422
    )
    assert client.get("/api/v1/tags").status_code == 401


def test_note_deletion_cascades_associations(app: FastAPI, client: TestClient, auth: dict) -> None:
    note_id = seed_note(app)
    client.post(f"/api/v1/notes/{note_id}/tags", headers=auth, json={"name": "保留标签"})
    assert client.delete(f"/api/v1/notes/{note_id}", headers=auth).status_code == 204
    with app.state.session_factory() as db:
        assert db.scalar(select(NoteTag)) is None
        assert db.scalar(select(Tag)).name == "保留标签"


def test_tag_normalization() -> None:
    assert TagRequest(name=" 工作\u3000灵感 ").name == "工作 灵感"


def test_organization_migration_backfills_and_preserves_notes(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    import json

    from alembic import command
    from alembic.config import Config
    from app.config import BACKEND_ROOT
    from sqlalchemy import text

    note_id = seed_note(app)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0005_platform_checks")
        connection.execute(
            text("UPDATE notes SET suggested_tags=:tags WHERE id=:id"),
            {"tags": json.dumps([" 知识管理 ", "知识管理", "", "写作"]), "id": note_id},
        )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
    note = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
    assert {tag["name"] for tag in note["tags"]} == {"知识管理", "写作"}
    assert note["is_favorite"] is False
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0005_platform_checks")
        assert connection.scalar(text("SELECT count(*) FROM notes")) == 1
        command.upgrade(config, "head")
    assert (
        client.get(f"/api/v1/notes/{note_id}", headers=auth).json()["content"]["text"] == "整理笔记"
    )
