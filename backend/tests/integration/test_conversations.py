# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from app.backup_repository import BackupRepository
from app.config import BACKEND_ROOT
from app.conversation_repository import ConversationRepository
from app.db.base import utcnow
from app.errors import ClipoError
from app.models import ConversationJob, Note, NoteConversation
from app.repositories import IdentityRepository
from app.schemas.backup import Archive
from app.security.credentials import create_access_token
from app.tasks.capture import CaptureQueue
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from tests.integration.test_backups import export_library
from tests.integration.test_note_organization import seed_note


class Model:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail

    def complete(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        if self.fail:
            raise ValueError("DO-NOT-ECHO-private-key-or-response")
        return "根据原文，**保留来源**。"


def configured(app: FastAPI, client: TestClient, auth: dict) -> tuple[int, Model]:
    note_id = seed_note(app)
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": "offline-only"}})
    model = Model()
    app.state.capture_queue.conversations.llm = model
    return note_id, model


def submit(
    client: TestClient, auth: dict, note_id: int, key: str = "first", question: str = "主要论点？"
) -> dict:
    response = client.post(
        f"/api/v1/notes/{note_id}/conversations",
        headers=auth,
        json={"question": question, "request_key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def history(client: TestClient, auth: dict, note_id: int, **params: int) -> dict:
    response = client.get(f"/api/v1/notes/{note_id}/conversations", headers=auth, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_persistent_context_idempotence_and_note_unchanged(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, model = configured(app, client, auth)
    before = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
    job = submit(client, auth, note_id)
    assert submit(client, auth, note_id)["id"] == job["id"]
    assert history(client, auth, note_id)["turns"][0]["role"] == "user"
    for _ in range(2):
        app.state.capture_queue.conversations.run(1, job["id"])
    assert len(model.calls) == 1
    article = json.loads(model.calls[0]["messages"][1]["content"].split("\n", 1)[1])
    assert article["text"] == before["content"]["text"]
    assert not model.calls[0]["json_mode"]
    second = submit(client, auth, note_id, "second", "具体怎么做？")
    app.state.capture_queue.conversations.run(1, second["id"])
    assert model.calls[-1]["messages"][-3:] == [
        {"role": "user", "content": "主要论点？"},
        {"role": "assistant", "content": "根据原文，**保留来源**。"},
        {"role": "user", "content": "具体怎么做？"},
    ]
    result = history(client, auth, note_id)
    assert [(m["turn_index"], m["role"]) for m in result["turns"]] == [
        (0, "user"),
        (0, "assistant"),
        (1, "user"),
        (1, "assistant"),
    ]
    assert result["latest_job"]["status"] == "success"
    page = history(client, auth, note_id, limit=1)
    assert page["next_before"] == 1
    assert [
        m["turn_index"] for m in history(client, auth, note_id, before=1, limit=1)["turns"]
    ] == [0, 0]
    assert submit(client, auth, note_id)["id"] == job["id"]
    assert client.get(f"/api/v1/notes/{note_id}", headers=auth).json() == before


def test_busy_and_key_conflicts(app: FastAPI, client: TestClient, auth: dict) -> None:
    note_id = seed_note(app)
    submit(client, auth, note_id)
    for identifier, key, question, code in (
        (note_id, "other", "another", "conversation_busy"),
        (note_id, "first", "changed", "idempotency_conflict"),
        (seed_note(app), "first", "主要论点？", "idempotency_conflict"),
    ):
        response = client.post(
            f"/api/v1/notes/{identifier}/conversations",
            headers=auth,
            json={"question": question, "request_key": key},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == code
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(NoteConversation)) == 1


def test_failed_retry_missing_config_and_redaction(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    job = submit(client, auth, note_id)
    queue = app.state.capture_queue.conversations
    assert queue.run(1, job["id"]) is None
    assert "模型密钥" in history(client, auth, note_id)["latest_job"]["last_error"]
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": "offline-only"}})
    assert (
        client.post(f"/api/v1/conversation-jobs/{job['id']}/retry", headers=auth).status_code == 202
    )
    queue.llm = Model(fail=True)
    for delay in (30, 120, 480, None):
        assert queue.run(1, job["id"]) == delay
        with app.state.session_factory.begin() as db:
            row = db.get(ConversationJob, job["id"])
            assert row.status == ("retrying" if delay else "failed")
            assert "DO-NOT-ECHO" not in row.last_error
            row.next_retry_at = utcnow() - timedelta(seconds=1)
    queue.llm = Model()
    assert (
        client.post(f"/api/v1/conversation-jobs/{job['id']}/retry", headers=auth).status_code == 202
    )
    queue.run(1, job["id"])
    assert len(history(client, auth, note_id)["turns"]) == 2
    assert (
        client.post(f"/api/v1/conversation-jobs/{job['id']}/retry", headers=auth).status_code == 409
    )


def test_failed_turn_is_excluded_from_context_and_cannot_retry_after_new_turn(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, model = configured(app, client, auth)
    job = submit(client, auth, note_id)
    with app.state.session_factory.begin() as db:
        db.get(ConversationJob, job["id"]).status = "failed"
    newer = submit(client, auth, note_id, "newer", "新问题")
    app.state.capture_queue.conversations.run(1, newer["id"])
    assert len(model.calls[0]["messages"]) == 4
    assert (
        client.post(f"/api/v1/conversation-jobs/{job['id']}/retry", headers=auth).status_code == 409
    )


def test_isolation_delete_and_late_model_completion(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, _ = configured(app, client, auth)
    job = submit(client, auth, note_id)
    with app.state.session_factory.begin() as db:
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    other = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    for method, path, payload in (
        ("GET", f"/notes/{note_id}/conversations", None),
        ("POST", f"/notes/{note_id}/conversations", {"question": "test", "request_key": "test"}),
        ("POST", f"/conversation-jobs/{job['id']}/retry", None),
    ):
        assert (
            client.request(method, "/api/v1" + path, headers=other, json=payload).status_code == 404
        )
        assert client.request(method, "/api/v1" + path, json=payload).status_code == 401
    with app.state.session_factory.begin() as db:
        repository = ConversationRepository(db, 1)
        assert repository.claim(job["id"], "old")
    assert client.delete(f"/api/v1/notes/{note_id}", headers=auth).status_code == 204
    with app.state.session_factory.begin() as db:
        ConversationRepository(db, 1).finish(job["id"], "old", "已删除后的回答")
        assert db.scalar(select(NoteConversation)) is None
        assert db.scalar(select(ConversationJob)) is None
    assert app.state.capture_queue.conversations.run(1, job["id"]) is None


def test_concurrency_recovery_and_execution_fence(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, model = configured(app, client, auth)

    def create(_: int) -> str:
        with app.state.session_factory.begin() as db:
            return ConversationRepository(db, 1).submit(note_id, "并发提问", "shared-key").id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(create, range(4)))
    assert len(set(ids)) == 1

    def competing(_: int) -> None:
        with pytest.raises(ClipoError, match="上一条问题"):
            with app.state.session_factory.begin() as db:
                ConversationRepository(db, 1).submit(note_id, "竞争", "competing")

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(competing, range(2)))
    with app.state.session_factory.begin() as db:
        repository = ConversationRepository(db, 1)
        assert repository.claim(ids[0], "old")
        assert repository.claim(ids[0], "duplicate") is None
        repository.job(ids[0]).lease_expires_at = utcnow() - timedelta(seconds=1)
    replacement = CaptureQueue(app.state.session_factory, app.state.settings)
    replacement.conversations.llm = model
    replacement.conversations.recover()
    task = replacement.huey.dequeue()
    assert task is not None
    replacement.huey.execute(task)
    with app.state.session_factory.begin() as db:
        repository = ConversationRepository(db, 1)
        repository.finish(ids[0], "old", "旧回答不得覆盖")
        repository.fail(ids[0], "old", "旧失败不得覆盖", None)
        assert repository.job(ids[0]).status == "success"
        assert [m.content for m in repository.completed(note_id)] == [
            "并发提问",
            "根据原文，**保留来源**。",
        ]


def test_last_lease_expiration_fails_without_more_model_calls(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, model = configured(app, client, auth)
    job = submit(client, auth, note_id)
    with app.state.session_factory.begin() as db:
        row = db.get(ConversationJob, job["id"])
        row.status, row.attempts = "running", 4
        row.lease_expires_at = utcnow() - timedelta(seconds=1)
    app.state.capture_queue.conversations.recover()
    assert history(client, auth, note_id)["latest_job"]["status"] == "failed"
    assert model.calls == []


@pytest.mark.parametrize("question", ["", "  \n", "字" * 4001, None, 42])
def test_invalid_questions(client: TestClient, auth: dict, question: object) -> None:
    response = client.post(
        "/api/v1/notes/1/conversations",
        headers=auth,
        json={"question": question, "request_key": "test"},
    )
    assert response.status_code == 422
    assert "input" not in response.text


def test_shared_rate_limit(app: FastAPI, client: TestClient, auth: dict) -> None:
    note_id = seed_note(app)
    for _ in range(10):
        submit(client, auth, note_id)
    response = client.post(
        f"/api/v1/notes/{note_id}/conversations",
        headers=auth,
        json={"question": "主要论点？", "request_key": "first"},
    )
    assert response.status_code == 429


def test_backup_roundtrip_old_archive_validation_and_private_boundaries(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, _ = configured(app, client, auth)
    job = submit(client, auth, note_id)
    app.state.capture_queue.conversations.run(1, job["id"])
    submit(client, auth, note_id, "pending", "尚未回答")
    _, data = export_library(app, client, auth)
    saved = data["notes"][0]["conversations"]
    assert len(saved) == 2 and "id" not in saved[0]
    with app.state.session_factory.begin() as db:
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
        BackupRepository(db, 2).restore(Archive.model_validate(data))
        note = db.scalar(select(Note).where(Note.user_id == 2))
        repository = ConversationRepository(db, 2)
        assert repository.history(note.id, None, 20).model_dump(mode="json")["turns"] == saved
        assert repository.submit(note.id, "恢复后继续", "restore").turn_index == 1
    detail = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
    assert "conversations" not in detail
    for format in ("markdown", "html"):
        exported = client.get(f"/api/v1/notes/{note_id}/export/{format}", headers=auth)
        assert "主要论点？" not in exported.text
    data["notes"][0]["conversations"] = [saved[0]]
    with pytest.raises(ValidationError):
        Archive.model_validate(data)
    data["notes"][0].pop("conversations")
    assert Archive.model_validate(data).notes[0].conversations == []


def test_migration_roundtrip(app: FastAPI, client: TestClient, auth: dict) -> None:
    note_id = seed_note(app)
    submit(client, auth, note_id)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0020_memory_gallery")
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
    assert history(client, auth, note_id)["turns"] == []
    assert client.get(f"/api/v1/notes/{note_id}", headers=auth).status_code == 200
