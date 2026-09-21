from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from app.models import CaptureJob, Comment
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_note_organization import seed_note


def test_deleted_ids_are_never_reused(app: FastAPI, client: TestClient, auth: dict) -> None:
    deleted = seed_note(app)
    assert client.delete(f"/api/v1/notes/{deleted}", headers=auth).status_code == 204
    created = seed_note(app)
    assert created > deleted
    assert client.delete(f"/api/v1/notes/{deleted}", headers=auth).status_code == 404
    assert client.get(f"/api/v1/notes/{created}", headers=auth).status_code == 200


def test_stable_ids_migration_preserves_dependents_and_search(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    client.post(f"/api/v1/notes/{note_id}/tags", headers=auth, json={"name": "迁移保留"})
    with app.state.session_factory.begin() as db:
        db.add(Comment(note_id=note_id, content="保留已有评论", position=0))
        job_id = db.scalar(select(CaptureJob.id).where(CaptureJob.note_id == note_id))
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    for target in ("0007_note_search", "head", "head"):
        with app.state.engine.begin() as connection:
            config.attributes["connection"] = connection
            if target == "head":
                command.upgrade(config, target)
                command.check(config)
            else:
                command.downgrade(config, target)
        note = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
        assert note["comments"][0]["content"] == "保留已有评论"
        assert note["tags"][0]["name"] == "迁移保留"
        assert client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()["note_id"] == note_id
        assert (
            client.get("/api/v1/notes?q=整理笔记", headers=auth).json()["items"][0]["id"] == note_id
        )
