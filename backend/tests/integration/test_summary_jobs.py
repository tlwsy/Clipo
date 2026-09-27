# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from app.db.base import utcnow
from app.llm.orchestrator import Summary, SummaryResult
from app.models import Comment, Note, SummaryJob
from app.repositories import IdentityRepository
from app.security.credentials import create_access_token
from app.summary_repository import SummaryRepository
from app.tasks.capture import CaptureQueue
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.integration.test_note_organization import seed_note


class Model:
    def __init__(self, scores: bool = True, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.scores, self.fail = scores, fail

    def complete(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("DO-NOT-ECHO-model-secret")
        return json.dumps(
            {
                "summary_markdown": "新的摘要内容",
                "key_points": ["新要点"],
                "suggested_tags": ["新标签"],
                "comment_insights": [{"text": "整合的操作建议", "indices": [0]}],
                "comment_scores": (
                    [{"index": 0, "score": 0.85, "reason": "补充经验"}] if self.scores else []
                ),
            }
        )


def submit(client: TestClient, auth: dict, note_id: int, key: str = "request") -> dict:
    response = client.post(
        f"/api/v1/notes/{note_id}/summarize", headers=auth, json={"request_key": key}
    )
    assert response.status_code == 202, response.text
    return response.json()


def configured(app: FastAPI, client: TestClient, auth: dict) -> tuple[int, Model]:
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        note = db.get(Note, note_id)
        note.summary_markdown, note.status, note.is_favorite = "旧摘要", "ready", True
        note.content = {**note.content, "raw_html": "<p>保留快照</p>"}
        db.add(
            Comment(
                note_id=note_id,
                position=0,
                content="这条评论提供完整操作步骤",
                likes=8,
                replies=0,
                ai_score=0.7,
                ai_reason="旧评分",
                is_valuable=True,
            )
        )
    client.post(f"/api/v1/notes/{note_id}/tags", headers=auth, json={"name": "手动标签"})
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": "test-only-key"}})
    model = Model()
    app.state.capture_queue.summaries.llm = model
    return note_id, model


def test_regenerate_in_place_preserves_content_and_organization(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, model = configured(app, client, auth)
    before = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
    job = submit(client, auth, note_id)
    assert submit(client, auth, note_id, "another")["id"] == job["id"]
    for _ in range(2):
        app.state.capture_queue.summaries.run(1, job["id"])
    after = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
    assert after["summary_markdown"] == "新的摘要内容"
    assert after["comment_insights"] == [{"text": "整合的操作建议", "indices": [0]}]
    for field in ("id", "url", "title", "content", "source", "created_at", "is_favorite"):
        assert before[field] == after[field]
    assert {tag["name"] for tag in after["tags"]} == {"手动标签", "新标签"}
    assert after["comments"][0]["ai_score"] == 0.85
    assert before["comments"][0]["id"] == after["comments"][0]["id"]
    assert len(model.calls) == 1
    assert json.loads(model.calls[0]["messages"][1]["content"])["comments"][0]["index"] == 0
    assert client.get("/api/v1/notes?q=新的摘要", headers=auth).json()["items"][0]["id"] == note_id
    assert submit(client, auth, note_id)["id"] == job["id"]
    assert submit(client, auth, note_id, "another")["id"] == job["id"]
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Note)) == 1
        assert db.get(Note, note_id).content["raw_html"] == "<p>保留快照</p>"


def test_merged_key_cannot_be_reused_for_another_note(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    first, second = seed_note(app), seed_note(app)
    job = submit(client, auth, first, "first")
    assert submit(client, auth, first, "merged")["id"] == job["id"]
    response = client.post(
        f"/api/v1/notes/{second}/summarize", headers=auth, json={"request_key": "merged"}
    )
    assert response.status_code == 409
    app.state.capture_queue.summaries.run(1, job["id"])
    assert submit(client, auth, first, "merged")["id"] == job["id"]


def test_summary_key_migration_backfills_existing_jobs(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    job = submit(client, auth, note_id)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0014_access_buckets")
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
    assert submit(client, auth, note_id)["id"] == job["id"]


def test_missing_model_fails_then_manual_retry_and_scoring_failure_preserves_scores(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, _ = configured(app, client, auth)
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": ""}})
    # Explicitly remove the key, independently of settings' retain-empty behavior.
    with app.state.session_factory.begin() as db:
        settings = SummaryRepository(db, 1).settings()
        settings.llm_config = {
            key: value for key, value in settings.llm_config.items() if key != "api_key"
        }
    job = submit(client, auth, note_id)
    assert app.state.capture_queue.summaries.run(1, job["id"]) is None
    failed = client.get(f"/api/v1/summary-jobs/{job['id']}", headers=auth).json()
    assert failed["status"] == "failed" and "模型密钥" in failed["last_error"]
    assert (
        client.get(f"/api/v1/notes/{note_id}", headers=auth).json()["summary_markdown"] == "旧摘要"
    )
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": "test-only"}})
    assert client.post(f"/api/v1/summary-jobs/{job['id']}/retry", headers=auth).status_code == 202
    app.state.capture_queue.summaries.llm = Model(scores=False)
    app.state.capture_queue.summaries.run(1, job["id"])
    after = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
    assert after["summary_markdown"] == "新的摘要内容"
    assert after["comments"][0]["ai_score"] == 0.7
    assert after["comment_score_error"]
    assert client.post(f"/api/v1/summary-jobs/{job['id']}/retry", headers=auth).status_code == 409


def test_failures_retry_without_losing_old_results(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, _ = configured(app, client, auth)
    app.state.capture_queue.summaries.llm = Model(fail=True)
    job = submit(client, auth, note_id)
    for delay in (30, 120, 480, None):
        assert app.state.capture_queue.summaries.run(1, job["id"]) == delay
        with app.state.session_factory.begin() as db:
            row = db.get(SummaryJob, job["id"])
            assert row.status == ("retrying" if delay else "failed")
            assert "DO-NOT-ECHO" not in row.last_error
            row.next_retry_at = utcnow() - timedelta(seconds=1)
    after = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
    assert after["summary_markdown"] == "旧摘要" and after["comments"][0]["ai_score"] == 0.7
    newer = submit(client, auth, note_id, "newer")
    assert newer["id"] != job["id"]
    assert client.post(f"/api/v1/summary-jobs/{job['id']}/retry", headers=auth).status_code == 409


def test_summary_jobs_isolate_accounts_and_delete_cascades(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    job = submit(client, auth, note_id)
    with app.state.session_factory.begin() as db:
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    other = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    for method, path, body in (
        ("GET", f"/notes/{note_id}/summary-job", None),
        ("POST", f"/notes/{note_id}/summarize", {"request_key": "test"}),
        ("GET", f"/summary-jobs/{job['id']}", None),
        ("POST", f"/summary-jobs/{job['id']}/retry", None),
    ):
        assert client.request(method, "/api/v1" + path, headers=other, json=body).status_code == 404
        assert client.request(method, "/api/v1" + path, json=body).status_code == 401
    assert client.delete(f"/api/v1/notes/{note_id}", headers=auth).status_code == 204
    assert app.state.capture_queue.summaries.run(1, job["id"]) is None
    assert client.get(f"/api/v1/summary-jobs/{job['id']}", headers=auth).status_code == 404


def test_fencing_restart_recovery_and_concurrent_submission(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id, model = configured(app, client, auth)

    def create(index: int) -> str:
        with app.state.session_factory.begin() as db:
            return SummaryRepository(db, 1).submit_summary(note_id, f"concurrent-{index}").id

    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(pool.map(create, range(4)))
    assert len(set(identifiers)) == 1
    job_id = identifiers[0]
    with app.state.session_factory.begin() as db:
        repository = SummaryRepository(db, 1)
        assert repository.claim_summary(job_id, "old")
        assert repository.claim_summary(job_id, "duplicate") is None
        repository.summary_job(job_id).lease_expires_at = utcnow() - timedelta(seconds=1)
    replacement = CaptureQueue(app.state.session_factory, app.state.settings)
    replacement.summaries.llm = model
    replacement.recover()
    task = replacement.huey.dequeue()
    assert task is not None
    replacement.huey.execute(task)
    with app.state.session_factory.begin() as db:
        repository = SummaryRepository(db, 1)
        assert repository.summary_job(job_id).status == "success"
        repository.finish_summary(
            job_id, "old", SummaryResult(Summary(summary_markdown="过期结果", key_points=[]))
        )
        assert repository.note(note_id).summary_markdown == "新的摘要内容"


def test_summary_migration_preserves_notes(app: FastAPI, client: TestClient, auth: dict) -> None:
    note_id = seed_note(app)
    submit(client, auth, note_id)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0011_backup_jobs")
        command.upgrade(config, "head")
        command.check(config)
    assert client.get(f"/api/v1/notes/{note_id}", headers=auth).status_code == 200
    assert client.get(f"/api/v1/notes/{note_id}/summary-job", headers=auth).json() is None
