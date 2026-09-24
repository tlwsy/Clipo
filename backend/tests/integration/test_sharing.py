# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from app.db.base import utcnow
from app.errors import ClipoError
from app.models import Comment, Note, SharedLink
from app.repositories import IdentityRepository
from app.security.credentials import create_access_token, hash_token
from app.sharing_repository import SharingRepository
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.integration.test_backups import export_library
from tests.integration.test_note_organization import seed_note


def issue(client: TestClient, auth: dict, note_id: int, days: int | None = 7) -> dict:
    response = client.post(
        f"/api/v1/notes/{note_id}/shares", headers=auth, json={"expires_in_days": days}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_public_read_has_only_allowed_fields_and_hashed_capability(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        note = db.get(Note, note_id)
        note.content = {
            **note.content,
            "selection": "private-selection",
            "raw_html": "private-html",
            "capture_warnings": ["private-warning"],
            "images": ["https://example.com/a.jpg"],
        }
        note.summary_error = "private-error"
        note.is_favorite = True
        note.suggested_tags = ["private-tags"]
        db.add(
            Comment(
                note_id=note_id,
                position=0,
                content="评论正文",
                likes=5,
                replies=1,
                ai_score=0.9,
                ai_reason="评分理由",
                is_valuable=True,
            )
        )
    link = issue(client, auth, note_id)
    assert len(link["token"]) == 43
    with app.state.session_factory() as db:
        row = db.get(SharedLink, link["id"])
        assert row.token_hash == hash_token(link["token"]) and row.token_hash != link["token"]
        assert timedelta(days=6) < row.expires_at - utcnow() <= timedelta(days=7)
    response = client.post("/api/v1/public/notes/read", json={"token": link["token"]})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
    assert set(response.json()) == {
        "title",
        "url",
        "platform",
        "author",
        "published_at",
        "text",
        "images",
        "summary_markdown",
        "key_points",
        "comments",
    }
    assert response.json()["comments"][0]["ai_score"] == 0.9
    assert "id" not in response.json()["comments"][0]
    assert "private-" not in response.text
    listing = client.get(f"/api/v1/notes/{note_id}/shares", headers=auth)
    assert link["token"] not in listing.text and "token_hash" not in listing.text
    assert listing.json()[0]["id"] == link["id"]
    assert client.get(f"/api/v1/notes/{note_id}").status_code == 401


def test_revoke_expiry_and_deletion_make_links_indistinguishable(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    first, second, third = [issue(client, auth, note_id, days) for days in (None, 1, 30)]
    with app.state.session_factory.begin() as db:
        db.get(SharedLink, second["id"]).expires_at = utcnow() - timedelta(seconds=1)
        db.get(Note, note_id).summary_markdown = "分享后更新的摘要"
    assert (
        client.post("/api/v1/public/notes/read", json={"token": first["token"]}).json()[
            "summary_markdown"
        ]
        == "分享后更新的摘要"
    )
    path = f"/api/v1/notes/{note_id}/shares/{first['id']}"
    for _ in range(2):
        assert client.delete(path, headers=auth).status_code == 204
    listing = client.get(f"/api/v1/notes/{note_id}/shares", headers=auth).json()
    assert [row["id"] for row in listing] == [third["id"]]
    assert client.delete(f"/api/v1/notes/{note_id}", headers=auth).status_code == 204
    failures = [
        client.post("/api/v1/public/notes/read", json={"token": token})
        for token in (first["token"], second["token"], third["token"], "x" * 43)
    ]
    assert all(response.status_code == 404 for response in failures)
    assert all(response.json() == failures[0].json() for response in failures)


def test_share_management_requires_owner_and_excludes_credentials_from_backup(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    link = issue(client, auth, note_id)
    with app.state.session_factory.begin() as db:
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
    other = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    for method, path, body in (
        ("GET", f"/notes/{note_id}/shares", None),
        ("POST", f"/notes/{note_id}/shares", {}),
        ("DELETE", f"/notes/{note_id}/shares/{link['id']}", None),
    ):
        assert client.request(method, "/api/v1" + path, headers=other, json=body).status_code == 404
        assert client.request(method, "/api/v1" + path, json=body).status_code == 401
    _, archive = export_library(app, client, auth)
    assert link["token"] not in str(archive) and link["id"] not in str(archive)
    assert "token_hash" not in str(archive)
    for days in (-1, 0, 2, "forever"):
        assert (
            client.post(
                f"/api/v1/notes/{note_id}/shares", headers=auth, json={"expires_in_days": days}
            ).status_code
            == 422
        )
    invalid = client.post("/api/v1/public/notes/read", json={"token": "DO-NOT-ECHO"})
    assert invalid.status_code == 422 and "DO-NOT-ECHO" not in invalid.text
    assert client.get(f"/api/v1/public/notes/{note_id}").status_code == 404


def test_public_urls_are_safe_even_for_legacy_content(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        note = db.get(Note, note_id)
        note.url = "javascript:alert(1)"
        note.content = {
            **note.content,
            "images": [
                "javascript:alert(1)",
                "http://127.0.0.1/private",
                "https://example.com/safe.jpg",
            ],
        }
    link = issue(client, auth, note_id)
    body = client.post("/api/v1/public/notes/read", json={"token": link["token"]}).json()
    assert body["url"] is None and body["images"] == ["https://example.com/safe.jpg"]


def test_share_count_is_bounded_under_concurrent_creation(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    for _ in range(8):
        issue(client, auth, note_id)

    def create(_: int) -> str:
        try:
            with app.state.session_factory.begin() as db:
                return SharingRepository(db, 1).create_share(note_id, 7)[0].id
        except ClipoError as exc:
            assert exc.code == "share_limit"
            return "limited"

    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(pool.map(create, range(4)))
    assert identifiers.count("limited") == 2
    links = client.get(f"/api/v1/notes/{note_id}/shares", headers=auth).json()
    assert len(links) == 10
    client.delete(f"/api/v1/notes/{note_id}/shares/{links[0]['id']}", headers=auth)
    issue(client, auth, note_id)


def test_share_migration_preserves_notes(app: FastAPI, client: TestClient, auth: dict) -> None:
    note_id = seed_note(app)
    link = issue(client, auth, note_id)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0012_summary_jobs")
        command.upgrade(config, "head")
        command.check(config)
    assert client.get(f"/api/v1/notes/{note_id}", headers=auth).status_code == 200
    assert (
        client.post("/api/v1/public/notes/read", json={"token": link["token"]}).status_code == 404
    )
