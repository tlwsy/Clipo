# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import anyio
import pytest
from alembic import command
from alembic.config import Config
from app.api.note_guard import NOTE_BODY_BYTES, NoteAccessGuard
from app.config import BACKEND_ROOT
from app.db.base import utcnow
from app.errors import ClipoError
from app.models import AccessBucket
from app.repositories import IdentityRepository
from app.security import note_limits
from app.security.credentials import create_access_token
from app.security.note_limits import NoteRateLimiter
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from starlette.types import Message, Receive, Scope, Send
from tests.integration.test_note_organization import seed_note


def test_summary_and_share_limits_are_per_account_and_allow_revocation(
    app: FastAPI, client: TestClient, auth: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(note_limits, "SUMMARY_LIMIT", 2)
    monkeypatch.setattr(note_limits, "SHARE_LIMIT", 2)
    note_id = seed_note(app)
    path = f"/api/v1/notes/{note_id}"
    for _ in range(2):
        assert (
            client.post(path + "/summarize", headers=auth, json={"request_key": "same"}).status_code
            == 202
        )
    limited = client.post(path + "/summarize", headers=auth, json={"request_key": "new"})
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0
    assert limited.json()["error"]["detail"]["retry_after"] <= 60
    assert client.get(path + "/summary-job", headers=auth).status_code == 200
    links = [client.post(path + "/shares", headers=auth, json={}) for _ in range(2)]
    assert all(response.status_code == 201 for response in links)
    assert client.post(path + "/shares", headers=auth, json={}).status_code == 429
    assert client.delete(path + "/shares/" + links[0].json()["id"], headers=auth).status_code == 204
    with app.state.session_factory.begin() as db:
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    other_note = seed_note(app, 2)
    other = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    assert (
        client.post(
            f"/api/v1/notes/{other_note}/summarize", headers=other, json={"request_key": "new"}
        ).status_code
        == 202
    )
    assert (
        client.post(f"/api/v1/notes/{other_note}/shares", headers=other, json={}).status_code == 201
    )
    with app.state.session_factory.begin() as db:
        db.execute(update(AccessBucket).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert (
        client.post(path + "/summarize", headers=auth, json={"request_key": "new"}).status_code
        == 202
    )


def test_api_token_can_submit_without_nested_transaction_lock(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    token = client.post("/api/v1/tokens", headers=auth, json={"name": "summary"}).json()["token"]
    headers = {"X-Clipo-Token": token}
    assert (
        client.post(
            f"/api/v1/notes/{note_id}/summarize",
            headers=headers,
            json={"request_key": "from-token"},
        ).status_code
        == 202
    )
    assert (
        client.post(f"/api/v1/notes/{note_id}/shares", headers=headers, json={}).status_code == 201
    )


def test_public_limit_counts_invalid_requests_and_ignores_untrusted_forwarded_headers(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(note_limits, "PUBLIC_CLIENT_LIMIT", 2)
    for _ in range(2):
        assert client.post("/api/v1/public/notes/read", content="invalid JSON").status_code == 422
    response = client.post(
        "/api/v1/public/notes/read",
        json={"token": "x" * 43},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert response.status_code == 429
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Retry-After"] == str(response.json()["error"]["detail"]["retry_after"])
    assert client.get("/api/v1/health").status_code == 200
    with app.state.session_factory() as db:
        rows = list(db.scalars(select(AccessBucket)))
        assert len(rows) == 2 and all(len(row.key) == 64 for row in rows)
        assert "testclient" not in str([row.key for row in rows])


def test_global_limit_bounds_distinct_client_growth_and_survives_recreation(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(note_limits, "PUBLIC_GLOBAL_LIMIT", 3)
    limiter = app.state.note_limiter
    for address in ("one", "two", "three"):
        limiter.public_read(address)
    replacement = NoteRateLimiter(
        app.state.session_factory, app.state.settings.secret_key.get_secret_value()
    )
    for address in ("four", "five"):
        with pytest.raises(ClipoError) as caught:
            replacement.public_read(address)
        assert caught.value.status == 429
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AccessBucket)) == 4


def test_rate_limit_is_atomic_under_concurrency(app: FastAPI) -> None:
    def consume(_: int) -> bool:
        limiter = NoteRateLimiter(app.state.session_factory, "test-secret")
        try:
            limiter.consume([("concurrent", 3)])
            return True
        except ClipoError as exc:
            assert exc.status == 429
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(consume, range(12)))
    assert sum(results) == 3


def test_note_request_bodies_are_bounded_before_validation(client: TestClient, auth: dict) -> None:
    for path in (
        "/public/notes/read",
        "/notes/1/summarize",
        "/notes/1/shares",
        "/summary-jobs/id/retry",
    ):
        response = client.post("/api/v1" + path, content=b"x" * (NOTE_BODY_BYTES + 1), headers=auth)
        assert response.status_code == 413 and response.headers["Cache-Control"] == "no-store"
        assert "x" * 100 not in response.text


def test_chunked_body_stops_before_the_application(app: FastAPI) -> None:
    called = False
    received: list[Message] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal called
        called = True

    async def run() -> None:
        messages = iter(
            [
                {"type": "http.request", "body": b"x" * NOTE_BODY_BYTES, "more_body": True},
                {"type": "http.request", "body": b"x", "more_body": True},
            ]
        )

        async def receive() -> Message:
            return next(messages)

        async def send(message: Message) -> None:
            received.append(message)

        middleware = NoteAccessGuard(downstream, app.state.note_limiter)
        await middleware(
            {"type": "http", "method": "POST", "path": "/api/v1/notes/1/shares"}, receive, send
        )

    anyio.run(run)
    assert not called and received[0]["status"] == 413


def test_note_limits_migration_preserves_notes(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    app.state.note_limiter.summary(1)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0013_shared_links")
        command.upgrade(config, "head")
        command.check(config)
    assert client.get(f"/api/v1/notes/{note_id}", headers=auth).status_code == 200
    app.state.note_limiter.summary(1)
