# SPDX-License-Identifier: AGPL-3.0-or-later
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from app.model_usage_repository import ModelQuotaExceeded, ModelUsageRepository
from app.models import ModelUsage, UserSettings
from app.repositories import IdentityRepository
from app.security.credentials import create_access_token
from app.services.model_usage import reserve_model_call
from app.tasks.capture import CaptureQueue
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from tests.integration import test_conversations as conversations
from tests.integration import test_payload_capture as captures
from tests.integration import test_semantic_search as embeddings
from tests.integration import test_summary_jobs as summaries

PATH = "/api/v1/settings/model-usage"


def limit(client: TestClient, auth: dict, value: int | None) -> dict:
    response = client.put(PATH, headers=auth, json={"monthly_limit": value})
    assert response.status_code == 200, response.text
    return response.json()


def status(client: TestClient, auth: dict) -> dict:
    response = client.get(PATH, headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


def test_defaults_account_isolation_and_validation(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    assert client.get(PATH).status_code == 401
    assert client.put(PATH, json={"monthly_limit": 0}).status_code == 401
    assert status(client, auth)["monthly_limit"] is None
    for payload in (
        {},
        {"monthly_limit": -1},
        {"monthly_limit": True},
        {"monthly_limit": 1.5},
        {"monthly_limit": "2"},
        {"monthly_limit": 1000001},
        {"monthly_limit": 2, "calls": 0},
    ):
        assert client.put(PATH, headers=auth, json=payload).status_code == 422
    limit(client, auth, 1)
    reserve_model_call(app.state.session_factory, 1)
    with app.state.session_factory.begin() as db:
        other = IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
        token = create_access_token(other.id, app.state.settings)
        other_id = other.id
    other_auth = {"Authorization": f"Bearer {token}"}
    assert status(client, other_auth)["calls"] == 0
    assert status(client, other_auth)["monthly_limit"] is None
    limit(client, other_auth, 0)
    with pytest.raises(ModelQuotaExceeded):
        reserve_model_call(app.state.session_factory, other_id)
    assert status(client, auth)["calls"] == 1
    assert status(client, auth)["monthly_limit"] == 1


def test_parallel_reservations_limit_changes_and_restart(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    limit(client, auth, 7)

    def consume(_: int) -> bool:
        try:
            reserve_model_call(app.state.session_factory, 1)
            return True
        except ModelQuotaExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(consume, range(20))) == 7
    assert status(client, auth)["calls"] == 7
    assert limit(client, auth, 3)["remaining"] == 0
    assert not consume(0)
    limit(client, auth, None)
    assert consume(0)
    assert limit(client, auth, 8)["remaining"] == 0
    replacement = CaptureQueue(app.state.session_factory, app.state.settings)
    with pytest.raises(ModelQuotaExceeded):
        reserve_model_call(replacement.sessions, 1)
    assert limit(client, auth, 9)["remaining"] == 1
    assert consume(0)
    assert status(client, auth)["calls"] == 9


def test_utc_month_rollover_retains_prior_usage(
    app: FastAPI, client: TestClient, auth: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    moment = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    monkeypatch.setattr("app.model_usage_repository.utcnow", lambda: moment)
    limit(client, auth, 1)
    reserve_model_call(app.state.session_factory, 1)
    result = status(client, auth)
    assert result["month"] == "2026-12"
    assert result["resets_at"] == "2027-01-01T00:00:00Z"
    moment = datetime(2027, 1, 1, tzinfo=UTC)
    assert status(client, auth)["calls"] == 0
    reserve_model_call(app.state.session_factory, 1)
    assert status(client, auth)["remaining"] == 0
    with app.state.session_factory() as db:
        assert (
            db.scalar(
                select(ModelUsage.calls).where(
                    ModelUsage.user_id == 1, ModelUsage.month == "2026-12"
                )
            )
            == 1
        )


def test_capture_preserves_original_and_comments_when_paused(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": "offline"}})
    model = summaries.Model()
    app.state.capture_queue.pipeline.llm = model
    job = captures.post(client, auth)
    # Enqueued work must observe a later quota edit before calling the model.
    limit(client, auth, 0)
    app.state.capture_queue.pipeline.run(1, job["job_id"])
    result = client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth).json()
    note = client.get(f"/api/v1/notes/{result['note_id']}", headers=auth).json()
    assert result["status"] == "success"
    assert note["content"]["text"] == captures.PAYLOAD["text"]
    assert note["comments"][0]["content"] == captures.PAYLOAD["comments"][0]["content"]
    assert "本月模型调用次数" in note["summary_error"]
    assert "本月模型调用次数" in note["comment_score_error"]
    assert model.calls == []
    assert status(client, auth)["calls"] == 0


def test_summary_internal_retry_counts_each_attempt_and_stops_at_quota(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note, _ = summaries.configured(app, client, auth)
    model = summaries.Model(fail=True)
    queue = app.state.capture_queue.summaries
    queue.llm = model
    limit(client, auth, 1)
    job = summaries.submit(client, auth, note)
    assert queue.run(1, job["id"]) is None
    assert len(model.calls) == 1
    with app.state.session_factory() as db:
        row = summaries.SummaryRepository(db, 1).summary_job(job["id"])
        assert row.status == "failed" and row.next_retry_at is None
        assert "本月模型调用次数" in row.last_error
    assert client.get(f"/api/v1/notes/{note}", headers=auth).json()["summary_markdown"] == "旧摘要"
    assert status(client, auth)["calls"] == 1


def test_partial_summary_kept_if_scoring_retry_exhausts_quota(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note, _ = summaries.configured(app, client, auth)
    model = summaries.Model(scores=False)
    queue = app.state.capture_queue.summaries
    queue.llm = model
    limit(client, auth, 1)
    job = summaries.submit(client, auth, note)
    assert queue.run(1, job["id"]) is None
    result = client.get(f"/api/v1/notes/{note}", headers=auth).json()
    assert result["summary_markdown"] == "新的摘要内容"
    assert result["comments"][0]["ai_score"] == 0.7
    assert "本月模型调用次数" in result["comment_score_error"]
    assert len(model.calls) == 1


def test_conversation_retry_idempotence_and_missing_key(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note, model = conversations.configured(app, client, auth)
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": ""}})
    job = conversations.submit(client, auth, note)
    queue = app.state.capture_queue.conversations
    assert queue.run(1, job["id"]) is None
    assert status(client, auth)["calls"] == 0
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": "offline"}})
    client.post(f"/api/v1/conversation-jobs/{job['id']}/retry", headers=auth)
    limit(client, auth, 0)
    assert queue.run(1, job["id"]) is None
    result = conversations.history(client, auth, note)
    assert len(result["turns"]) == 1
    assert result["latest_job"]["status"] == "failed"
    assert "本月模型调用次数" in result["latest_job"]["last_error"]
    assert model.calls == []
    limit(client, auth, 1)
    client.post(f"/api/v1/conversation-jobs/{job['id']}/retry", headers=auth)
    for _ in range(2):
        assert queue.run(1, job["id"]) is None
    assert conversations.submit(client, auth, note)["id"] == job["id"]
    assert len(model.calls) == status(client, auth)["calls"] == 1
    assert len(conversations.history(client, auth, note)["turns"]) == 2


def test_embeddings_backfill_query_cache_and_fulltext_fallback(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    embeddings.named_note(app, "专注训练")
    model = embeddings.configure(app, client, auth)
    limit(client, auth, 0)
    embeddings.drain(app)
    assert not model.calls
    assert status(client, auth)["calls"] == 0
    limit(client, auth, 2)
    assert client.post("/api/v1/settings/search-index", headers=auth).status_code == 202
    embeddings.drain(app)
    assert len(model.calls) == 1
    embeddings.search(client, auth)
    embeddings.drain(app)
    assert embeddings.search(client, auth)["semantic_status"] == "ready"
    assert len(model.calls) == status(client, auth)["calls"] == 2
    embeddings.search(client, auth, "专注", mode="semantic")
    embeddings.drain(app)
    result = embeddings.search(client, auth, "专注", mode="semantic")
    assert result["semantic_status"] == "failed"
    assert "本月模型调用次数" in result["message"]
    assert result["results"][0]["match_type"] == "fulltext"
    assert len(model.calls) == status(client, auth)["calls"] == 2


def test_migration_existing_accounts_usage_and_roundtrip(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0021_note_conversations")
        assert "model_usage" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
    assert status(client, auth)["monthly_limit"] is None
    reserve_model_call(app.state.session_factory, 1)
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.check(config)
    assert status(client, auth)["calls"] == 1
    with app.state.session_factory() as db:
        assert db.get(UserSettings, 1).monthly_model_limit is None
        assert ModelUsageRepository(db, 1).status().calls == 1


def test_all_features_share_one_account_budget(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": "offline"}})
    limit(client, auth, 3)
    queue = app.state.capture_queue
    summary_model = summaries.Model()
    queue.pipeline.llm = queue.summaries.llm = summary_model
    job = captures.post(client, auth)
    queue.pipeline.run(1, job["job_id"])
    note = client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth).json()["note_id"]
    summary_job = summaries.submit(client, auth, note)
    queue.summaries.run(1, summary_job["id"])
    conversation_model = conversations.Model(fail=True)
    queue.conversations.llm = conversation_model
    question = conversations.submit(client, auth, note)
    assert queue.conversations.run(1, question["id"]) == 30
    embedding_model = embeddings.configure(app, client, auth)
    embeddings.drain(app)
    assert len(summary_model.calls) == 2
    assert len(conversation_model.calls) == 1
    assert embedding_model.calls == []
    assert status(client, auth)["calls"] == 3
