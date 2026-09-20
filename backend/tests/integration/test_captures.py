import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from app.capture_repository import CaptureRepository
from app.db.base import utcnow
from app.extractors import generic
from app.extractors.base import CapturedComment, CapturedContent, ExtractionError
from app.llm.orchestrator import SummaryResult
from app.models import CaptureJob, Comment, ExtractionCache, Note, Source
from app.tasks.capture import CaptureQueue
from sqlalchemy import func, select

HTML = (Path(__file__).parents[1] / "fixtures" / "article.html").read_text()


@pytest.fixture
def offline(monkeypatch):
    calls = []

    def fetch(url):
        calls.append(url)
        return HTML, url

    monkeypatch.setattr(generic, "fetch_html", fetch)
    return calls


def submit(client, auth, url="https://example.com/article", key=None):
    response = client.post(
        "/api/v1/captures",
        headers={**auth, **({"Idempotency-Key": key} if key else {})},
        json={"url": url},
    )
    assert response.status_code == 202, response.text
    return response.json()


def execute(app):
    huey = app.state.capture_queue.huey
    task = huey.dequeue()
    assert task is not None
    huey.execute(task)


def test_url_to_note_via_durable_huey_without_llm(client, app, auth, offline):
    queued = submit(client, auth)
    assert queued["status"] == "queued"
    assert client.get("/api/v1/notes", headers=auth).json()["items"] == []
    execute(app)
    job = client.get(f"/api/v1/jobs/{queued['job_id']}", headers=auth).json()
    assert job["status"] == "success"
    assert job["attempts"] == 1
    note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()
    assert note["status"] == "original_only"
    assert "未生成摘要" in note["summary_error"]
    assert "保留来源" in note["content"]["text"]
    assert note["content"]["raw_html"] is None
    assert client.get("/api/v1/notes", headers=auth).json()["items"][0]["id"] == note["id"]
    with app.state.session_factory() as db:
        assert db.get(Note, note["id"]).content["raw_html"] == HTML
    assert len(offline) == 1


def test_llm_summary_uses_decrypted_settings_and_saves_key_points(client, app, auth, offline):
    calls = []

    class Model:
        def complete(self, **kwargs):
            calls.append(kwargs)
            return json.dumps(
                {
                    "summary_markdown": "## 笔记\n保留有用知识",
                    "key_points": ["保留来源", "定期回顾"],
                    "suggested_tags": ["知识管理"],
                }
            )

    app.state.capture_queue.pipeline.llm = Model()
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={"llm": {"api_key": "encrypted-model-secret", "model": "test-model"}},
    )
    queued = submit(client, auth)
    execute(app)
    job = client.get(f"/api/v1/jobs/{queued['job_id']}", headers=auth).json()
    note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()
    assert note["status"] == "ready"
    assert note["key_points"] == ["保留来源", "定期回顾"]
    assert calls[0]["api_key"] == "encrypted-model-secret"
    assert calls[0]["model"] == "test-model"


def test_idempotency_conflict_cache_expiry_and_pagination(client, app, auth, offline):
    first = submit(client, auth, key="first")
    assert (
        submit(client, auth, url="https://example.com/article#part", key="first")["job_id"]
        == first["job_id"]
    )
    conflict = client.post(
        "/api/v1/captures",
        headers={**auth, "Idempotency-Key": "first"},
        json={"url": "https://example.com/another"},
    )
    assert conflict.status_code == 409
    execute(app)
    execute(app)  # duplicate task must not produce another note
    second = submit(client, auth, key="second")
    assert second["cached"] is True
    execute(app)
    assert len(offline) == 1
    with app.state.session_factory.begin() as db:
        db.scalar(select(ExtractionCache)).expires_at = utcnow() - timedelta(seconds=1)
    assert not submit(client, auth)["cached"]
    execute(app)
    assert len(offline) == 2
    first_page = client.get("/api/v1/notes?limit=2", headers=auth).json()
    second_page = client.get(
        "/api/v1/notes", params={"limit": 2, "cursor": first_page["next_cursor"]}, headers=auth
    ).json()
    assert len(first_page["items"]) == 2 and len(second_page["items"]) == 1
    assert first_page["items"][0]["id"] != second_page["items"][0]["id"]
    assert client.get("/api/v1/notes?cursor=bogus", headers=auth).status_code == 422


def test_exponential_retries_exhaust_then_manual_retry(client, app, auth, monkeypatch, offline):
    def fail(url):
        raise ExtractionError("网页暂不可用，请稍后重试")

    monkeypatch.setattr(generic, "fetch_html", fail)
    queued = submit(client, auth)
    pipeline = app.state.capture_queue.pipeline
    for attempt, delay in enumerate([30, 120, 480, None], 1):
        assert pipeline.run(1, queued["job_id"]) == delay
        with app.state.session_factory.begin() as db:
            job = db.get(CaptureJob, queued["job_id"])
            assert job.attempts == attempt
            assert job.status == ("retrying" if delay else "failed")
            if delay:
                assert delay - 2 <= (job.next_retry_at - utcnow()).total_seconds() <= delay
                job.next_retry_at = utcnow() - timedelta(seconds=1)
    assert client.get("/api/v1/notes", headers=auth).json()["items"] == []
    monkeypatch.setattr(generic, "fetch_html", lambda url: (HTML, url))
    retry = client.post(f"/api/v1/jobs/{queued['job_id']}/retry", headers=auth)
    assert retry.status_code == 202
    assert retry.json()["attempts"] == 0
    pipeline.run(1, queued["job_id"])
    assert (
        client.get(f"/api/v1/jobs/{queued['job_id']}", headers=auth).json()["status"] == "success"
    )
    assert client.post(f"/api/v1/jobs/{queued['job_id']}/retry", headers=auth).status_code == 409


def test_user_isolation_includes_cache_jobs_notes_and_api_token(client, app, auth, offline):
    first = submit(client, auth, key="shared-key")
    execute(app)
    first = client.get(f"/api/v1/jobs/{first['job_id']}", headers=auth).json()
    app.state.settings.registration_open = True
    second_user = client.post(
        "/api/v1/auth/register",
        json={
            "username": "second",
            "email": "second@example.com",
            "password": "another-long-password",
        },
    ).json()
    second_auth = {"Authorization": "Bearer " + second_user["access_token"]}
    token = client.post(
        "/api/v1/tokens", headers=second_auth, json={"name": "capture-client"}
    ).json()["token"]
    headers = {"X-Clipo-Token": token}
    assert client.get("/api/v1/notes", headers=headers).json()["items"] == []
    assert client.get("/api/v1/jobs", headers=headers).json()["items"] == []
    for method, path in [
        ("get", f"/jobs/{first['job_id']}"),
        ("post", f"/jobs/{first['job_id']}/retry"),
        ("get", f"/notes/{first['note_id']}"),
        ("delete", f"/notes/{first['note_id']}"),
    ]:
        assert getattr(client, method)("/api/v1" + path, headers=headers).status_code == 404
    second = submit(client, headers, key="shared-key")
    assert second["job_id"] != first["job_id"] and not second["cached"]
    execute(app)
    assert len(offline) == 2


def test_queue_restart_and_outbox_recovery(client, app, auth, offline):
    job = submit(client, auth)
    replacement = CaptureQueue(app.state.session_factory, app.state.settings)
    replacement.huey.execute(replacement.huey.dequeue())
    assert client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth).json()["status"] == "success"
    missed = submit(client, auth, url="https://example.com/missed")
    replacement.huey.dequeue()  # simulate a crash after dequeue, before claiming
    replacement.recover()
    replacement.huey.execute(replacement.huey.dequeue())
    assert (
        client.get(f"/api/v1/jobs/{missed['job_id']}", headers=auth).json()["status"] == "success"
    )


def test_atomic_claim_fences_stale_workers_and_delete_cascades(client, app, auth):
    job = submit(client, auth)
    content = CapturedContent(
        url=job["url"],
        title="契约测试",
        text="原文",
        comments=[CapturedComment(author="甲", content="补充信息", likes=10)],
    )
    with app.state.session_factory.begin() as db:
        repository = CaptureRepository(db, 1)
        assert repository.claim(job["job_id"], "first")
    with app.state.session_factory.begin() as db:
        repository = CaptureRepository(db, 1)
        assert repository.claim(job["job_id"], "second") is None
        db.get(CaptureJob, job["job_id"]).lease_expires_at = utcnow() - timedelta(seconds=1)
    with app.state.session_factory.begin() as db:
        assert CaptureRepository(db, 1).claim(job["job_id"], "second")
    with app.state.session_factory.begin() as db:
        repository = CaptureRepository(db, 1)
        repository.finish(job["job_id"], "first", content, SummaryResult(None), False)
        assert db.scalar(select(func.count()).select_from(Note)) == 0
        repository.finish(job["job_id"], "second", content, SummaryResult(None), False)
    result = client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth).json()
    note = client.get(f"/api/v1/notes/{result['note_id']}", headers=auth).json()
    assert note["comments"][0]["likes"] == 10
    assert client.delete(f"/api/v1/notes/{result['note_id']}", headers=auth).status_code == 204
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Comment)) == 0
        assert db.scalar(select(func.count()).select_from(Source)) == 0
        assert db.get(CaptureJob, job["job_id"]).note_id is None


def test_concurrent_idempotency_creates_one_job(client, app, auth):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(client, auth, key="concurrent"), range(2)))
    assert results[0]["job_id"] == results[1]["job_id"]
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CaptureJob)) == 1


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1", "file:///etc/passwd", "https://user:pass@example.com"]
)
def test_capture_rejects_unsafe_url(client, auth, url):
    response = client.post("/api/v1/captures", headers=auth, json={"url": url})
    assert response.status_code == 422


def test_capture_requires_auth_and_rejects_unimplemented_payload(client, auth):
    assert client.post("/api/v1/captures", json={"url": "https://example.com"}).status_code == 401
    assert (
        client.post(
            "/api/v1/captures",
            headers=auth,
            json={"url": "https://example.com", "payload": {"text": "silent data loss"}},
        ).status_code
        == 422
    )


def test_model_failure_still_completes_note(client, app, auth, offline):
    class UnavailableModel:
        calls = 0

        def complete(self, **kwargs):
            self.calls += 1
            raise RuntimeError("sk-private-upstream-key")

    model = UnavailableModel()
    app.state.capture_queue.pipeline.llm = model
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": "key"}})
    queued = submit(client, auth)
    execute(app)
    job = client.get(f"/api/v1/jobs/{queued['job_id']}", headers=auth).json()
    assert job["status"] == "success" and job["attempts"] == 1
    note = client.get(f"/api/v1/notes/{job['note_id']}", headers=auth)
    assert note.json()["status"] == "original_only"
    assert "保留来源" in note.json()["content"]["text"]
    assert "sk-private" not in note.text
    assert model.calls == 2


def test_huey_persists_retry_and_recovery_exhausts_final_interruption(
    client, app, auth, monkeypatch
):
    def fail(url):
        raise ExtractionError("网络故障，请稍后重试")

    monkeypatch.setattr(generic, "fetch_html", fail)
    queued = submit(client, auth)
    execute(app)
    replacement = CaptureQueue(app.state.session_factory, app.state.settings)
    retry_task = replacement.huey.dequeue()
    assert retry_task is not None and retry_task.eta is not None
    replacement.huey.execute(retry_task)
    assert replacement.huey.scheduled_count() == 1
    with app.state.session_factory.begin() as db:
        job = db.get(CaptureJob, queued["job_id"])
        job.status = "running"
        job.attempts = 4
        job.lease_expires_at = utcnow() - timedelta(seconds=1)
    replacement.recover()
    result = client.get(f"/api/v1/jobs/{queued['job_id']}", headers=auth).json()
    assert result["status"] == "failed"
    assert "被中断" in result["last_error"]
