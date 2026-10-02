# SPDX-License-Identifier: AGPL-3.0-or-later
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from app.db.base import utcnow
from app.embedding_repository import EmbeddingRepository
from app.models import EmbeddingJob, Note
from app.services.embeddings import DIMENSIONS, EmbeddingConfig, load_embedding_config
from app.tasks.capture import CaptureQueue
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.integration.test_note_organization import seed_note


class Model:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail = False

    def embed(self, config: EmbeddingConfig, value: str) -> list[float]:
        self.calls.append(value)
        if self.fail:
            raise RuntimeError("DO-NOT-ECHO-secret-input-provider-body")
        focus = "专注" in value or "深度" in value
        return [1.0 if focus else 0.0, 0.0 if focus else 1.0] + [0.0] * (DIMENSIONS - 2)


def configure(app: FastAPI, client: TestClient, auth: dict) -> Model:
    response = client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "llm": {
                "embedding_enabled": True,
                "embedding_model": "test-embedding",
                "api_key": "offline-key",
            }
        },
    )
    assert response.status_code == 200, response.text
    model = Model()
    app.state.capture_queue.embeddings.client = model
    return model


def drain(app: FastAPI, user_id: int = 1) -> None:
    # Execute actual pipeline methods with a fixed model, never a real service.
    for _ in range(20):
        with app.state.session_factory() as db:
            jobs = list(
                db.scalars(
                    select(EmbeddingJob.id).where(
                        EmbeddingJob.user_id == user_id, EmbeddingJob.status == "queued"
                    )
                )
            )
        if not jobs:
            return
        for job in jobs:
            app.state.capture_queue.embeddings.run(user_id, job)
    raise AssertionError("Outbox did not settle")


def search(client: TestClient, auth: dict, query: str = "如何提高专注力", **params: object) -> dict:
    response = client.get("/api/v1/notes/search", headers=auth, params={"q": query, **params})
    assert response.status_code == 200, response.text
    return response.json()


def named_note(app: FastAPI, title: str, user_id: int = 1) -> int:
    identifier = seed_note(app, user_id)
    with app.state.session_factory.begin() as db:
        note = db.get(Note, identifier)
        note.title = title
        note.summary_markdown = "摘要：" + title
        note.key_points = ["要点：" + title]
    return identifier


def test_background_backfill_capture_query_rrf_and_filters(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    first = named_note(app, "深度工作与专注")
    other = named_note(app, "烹饪食谱")
    model = configure(app, client, auth)
    drain(app)
    assert len(model.calls) == 2
    status = client.get("/api/v1/settings/search-index", headers=auth).json()
    assert status["ready"] == status["total"] == 2
    assert status["pending"] == status["failed"] == 0
    result = search(client, auth)
    assert result["semantic_status"] == "queued"
    assert len(model.calls) == 2
    drain(app)
    result = search(client, auth)
    assert result["results"][0]["id"] == first
    assert result["results"][0]["match_type"] == "semantic"
    assert result["results"][0]["similarity"] == pytest.approx(1)
    search(client, auth)
    assert len(model.calls) == 3
    search(client, auth, "专注", mode="semantic")
    drain(app)
    hybrid = search(client, auth, "专注", mode="semantic")
    assert hybrid["results"][0]["match_type"] == "both"
    assert hybrid["results"][0]["score"] == pytest.approx(1)
    tag = client.post(f"/api/v1/notes/{other}/tags", headers=auth, json={"name": "食物"}).json()
    assert [row["id"] for row in search(client, auth, tag_id=tag["id"])["results"]] == [other]
    client.patch(f"/api/v1/notes/{first}", headers=auth, json={"is_favorite": True})
    assert [row["id"] for row in search(client, auth, favorite=True)["results"]] == [first]
    collection = client.post(
        "/api/v1/collections", headers=auth, json={"name": "工作", "color": "blue"}
    ).json()
    client.post(
        f"/api/v1/collections/{collection['id']}/notes", headers=auth, json={"note_ids": [first]}
    )
    assert [
        row["id"] for row in search(client, auth, collection_id=collection["id"])["results"]
    ] == [first]
    assert search(client, auth, collection_id=99999)["results"] == []
    third = named_note(app, "新采集笔记")
    drain(app)
    with app.state.session_factory() as db:
        assert db.get(Note, third).embedding_key
    client.post("/api/v1/settings/search-index", headers=auth)
    calls = len(model.calls)
    drain(app)
    assert len(model.calls) == calls


def test_isolation_deletion_defaults_quotes_and_validation(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    identifier = named_note(app, "deep work")
    named_note(app, "deep useful work")
    assert len(search(client, auth, '"deep work"')["results"]) == 1
    assert search(client, auth)["semantic_status"] == "disabled"
    configure(app, client, auth)
    drain(app)
    app.state.settings.registration_open = True
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "other",
            "email": "other@example.com",
            "password": "test-password-search",
        },
    ).json()
    other = {"Authorization": "Bearer " + response["access_token"]}
    configure(app, client, other)
    search(client, other)
    drain(app, response["user"]["id"])
    assert search(client, other)["results"] == []
    assert client.get("/api/v1/settings/search-index", headers=other).json()["total"] == 0
    assert client.get("/api/v1/notes/search?q=test").status_code == 401
    for query in ("", " ", '""', "x" * 201, "secret\ninput"):
        assert (
            client.get("/api/v1/notes/search", headers=auth, params={"q": query}).status_code == 422
        )
    search(client, auth)
    drain(app)
    client.delete(f"/api/v1/notes/{identifier}", headers=auth)
    assert identifier not in [row["id"] for row in search(client, auth)["results"]]
    with app.state.session_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(EmbeddingJob)
                .where(EmbeddingJob.note_id == identifier)
            )
            == 0
        )


def test_failures_recovery_fencing_configuration_and_expiry(
    app: FastAPI, client: TestClient, auth: dict, caplog: pytest.LogCaptureFixture
) -> None:
    identifier = named_note(app, "专注")
    model = configure(app, client, auth)
    model.fail = True
    drain(app)
    with app.state.session_factory() as db:
        job = db.scalar(select(EmbeddingJob).where(EmbeddingJob.note_id == identifier))
        job_id = job.id
        assert job.status == "retrying" and job.attempts == 1
    for _ in range(3):
        with app.state.session_factory.begin() as db:
            db.get(EmbeddingJob, job_id).next_retry_at = utcnow() - timedelta(seconds=1)
        app.state.capture_queue.embeddings.run(1, job_id)
    status = client.get("/api/v1/settings/search-index", headers=auth).json()
    assert status["failed"] == 1 and status["ready"] == 0
    assert "DO-NOT-ECHO" not in caplog.text
    detail = client.get(f"/api/v1/notes/{identifier}", headers=auth).json()
    assert detail["title"] == "专注" and "embedding" not in detail
    assert "DO-NOT-ECHO" not in str(detail)
    model.fail = False
    client.post("/api/v1/settings/search-index", headers=auth)
    drain(app)
    assert client.get("/api/v1/settings/search-index", headers=auth).json()["ready"] == 1
    search(client, auth)
    drain(app)
    calls = len(model.calls)
    with app.state.session_factory.begin() as db:
        query = db.scalar(select(EmbeddingJob).where(EmbeddingJob.kind == "query"))
        query.expires_at = utcnow() - timedelta(seconds=1)
    fresh = CaptureQueue(app.state.session_factory, app.state.settings)
    fresh.recover()
    search(client, auth)
    drain(app)
    assert len(model.calls) == calls + 1
    client.put("/api/v1/settings", headers=auth, json={"llm": {"embedding_model": "new-model"}})
    assert client.get("/api/v1/settings/search-index", headers=auth).json()["ready"] == 0
    drain(app)
    assert client.get("/api/v1/settings/search-index", headers=auth).json()["ready"] == 1


def test_atomic_claim_and_stale_worker_cannot_overwrite_new_generation(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    configure(app, client, auth)
    identifier = named_note(app, "专注")
    with app.state.session_factory() as db:
        job_id = db.scalar(select(EmbeddingJob.id).where(EmbeddingJob.note_id == identifier))

    def claim(execution: str) -> bool:
        with app.state.session_factory.begin() as db:
            return EmbeddingRepository(db, 1).claim(job_id, execution) is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ["a", "b"]))
    assert sorted(claims) == [False, True]
    with app.state.session_factory.begin() as db:
        repository = EmbeddingRepository(db, 1)
        config = load_embedding_config(repository, app.state.settings)
        note = repository.note(identifier)
        note.summary_markdown = "新摘要"
        repository.invalidate_note(note)
        repository.finish(job_id, "a", config, "stale", [1.0] * DIMENSIONS)
        assert repository.note(identifier).embedding_key is None
        assert repository.job(job_id) is None
    drain(app)
    with app.state.session_factory() as db:
        assert db.get(Note, identifier).embedding_key == config.key


def test_semantic_migration_upgrade_rollback_retains_notes(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    identifier = seed_note(app)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0018_annotations")
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
    assert client.get(f"/api/v1/notes/{identifier}", headers=auth).status_code == 200


def test_query_failure_degrades_and_rebuild_clears_failed_query_cache(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    identifier = named_note(app, "专注")
    model = configure(app, client, auth)
    drain(app)
    model.fail = True
    search(client, auth, "专注", mode="semantic")
    drain(app)
    for _ in range(2):
        with app.state.session_factory.begin() as db:
            job = db.scalar(select(EmbeddingJob).where(EmbeddingJob.kind == "query"))
            job.next_retry_at = utcnow() - timedelta(seconds=1)
            job_id = job.id
        app.state.capture_queue.embeddings.run(1, job_id)
    result = search(client, auth, "专注", mode="semantic")
    assert result["semantic_status"] == "failed"
    assert result["results"][0]["id"] == identifier
    assert result["results"][0]["match_type"] == "fulltext"
    assert "DO-NOT-ECHO" not in str(result)
    model.fail = False
    client.post("/api/v1/settings/search-index", headers=auth)
    search(client, auth, "专注", mode="semantic")
    drain(app)
    assert search(client, auth, "专注", mode="semantic")["semantic_status"] == "ready"


def test_interrupted_jobs_recover_and_exhaustion_is_visible(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    configure(app, client, auth)
    first, second = seed_note(app), seed_note(app)
    with app.state.session_factory.begin() as db:
        jobs = list(
            db.scalars(
                select(EmbeddingJob)
                .where(EmbeddingJob.kind == "note")
                .order_by(EmbeddingJob.note_id)
            )
        )
        for i, job in enumerate(jobs):
            job.status, job.execution_id = "running", "lost-worker"
            job.attempts = 1 if i == 0 else 4
            job.lease_expires_at = utcnow() - timedelta(seconds=1)
        first_job = jobs[0].id
    app.state.capture_queue.embeddings.recover()
    app.state.capture_queue.embeddings.run(1, first_job)
    with app.state.session_factory() as db:
        assert db.get(Note, first).embedding_key
        assert db.get(Note, second).embedding_error
        job = db.scalar(select(EmbeddingJob).where(EmbeddingJob.note_id == second))
        assert job.status == "failed"


def test_disabling_or_reconfiguring_while_model_runs_discards_old_result(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    configure(app, client, auth)
    identifier = named_note(app, "专注")

    class ChangingModel(Model):
        def embed(self, config: EmbeddingConfig, value: str) -> list[float]:
            client.put("/api/v1/settings", headers=auth, json={"llm": {"embedding_enabled": False}})
            return super().embed(config, value)

    app.state.capture_queue.embeddings.client = ChangingModel()
    drain(app)
    with app.state.session_factory() as db:
        assert db.get(Note, identifier).embedding_key is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(EmbeddingJob)
                .where(EmbeddingJob.note_id == identifier)
            )
            == 0
        )
    assert search(client, auth)["semantic_status"] == "disabled"


def test_backfill_multiple_batches_and_summary_refresh(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    identifiers = [seed_note(app) for _ in range(51)]
    model = configure(app, client, auth)
    drain(app)
    assert len(model.calls) == 51
    status = client.get("/api/v1/settings/search-index", headers=auth).json()
    assert status["ready"] == 51 and not status["backfill_running"]
    from tests.integration.test_summary_jobs import Model as SummaryModel

    app.state.capture_queue.summaries.llm = SummaryModel()
    job = client.post(
        f"/api/v1/notes/{identifiers[0]}/summarize", headers=auth, json={"request_key": "refresh"}
    ).json()
    app.state.capture_queue.summaries.run(1, job["id"])
    with app.state.session_factory() as db:
        assert db.get(Note, identifiers[0]).embedding_key is None
    drain(app)
    assert len(model.calls) == 52
    assert "新的摘要内容" in model.calls[-1]


def test_backup_excludes_vectors_and_restore_queues_new_user_owned_vectors(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    from tests.integration.test_backups import export_library

    seed_note(app)
    configure(app, client, auth)
    drain(app)
    _, archive = export_library(app, client, auth)
    assert not any("embedding" in key for key in archive["notes"][0])
    job = client.post("/api/v1/backups/imports", headers=auth, json=archive).json()
    app.state.capture_queue.backups.run(1, job["id"])
    with app.state.session_factory() as db:
        imported = db.scalar(select(Note).order_by(Note.id.desc()))
        assert imported.embedding_key is None
        queued = db.scalar(select(EmbeddingJob).where(EmbeddingJob.note_id == imported.id))
        assert queued.user_id == imported.user_id and queued.status == "queued"
    drain(app)
    assert client.get("/api/v1/settings/search-index", headers=auth).json()["ready"] == 2


def test_semantic_only_endpoint_and_shared_request_limit(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    configure(app, client, auth)
    named_note(app, "专注")
    drain(app)
    response = client.get("/api/v1/notes/search/semantic", headers=auth, params={"q": "专注"})
    assert response.status_code == 200
    assert response.json()["results"] == []
    drain(app)
    response = client.get("/api/v1/notes/search/semantic", headers=auth, params={"q": "专注"})
    assert response.json()["results"][0]["match_type"] == "semantic"
    for _ in range(118):
        app.state.note_limiter.consume([("search:user:1", 120)])
    limited = client.get("/api/v1/notes/search", headers=auth, params={"q": "专注"})
    assert limited.status_code == 429 and limited.headers["retry-after"]


def test_concurrent_identical_queries_share_one_outbox_generation(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    configure(app, client, auth)

    def submit(_: int) -> str:
        with app.state.session_factory.begin() as db:
            repository = EmbeddingRepository(db, 1)
            config = load_embedding_config(repository, app.state.settings)
            return repository.request_query("并发相同问题", config).id

    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(pool.map(submit, range(4)))
    assert len(set(identifiers)) == 1
    with app.state.session_factory() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(EmbeddingJob).where(EmbeddingJob.kind == "query")
            )
            == 1
        )
