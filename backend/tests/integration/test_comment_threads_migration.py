# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from app.models import Comment, UserSettings
from app.security.credentials import decrypt_secret
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from test_note_organization import seed_note


def test_upgrade_and_rollback_preserve_notes_scores_and_encrypted_cookies(
    app: FastAPI, client: TestClient, auth: dict[str, str]
) -> None:
    note_id = seed_note(app)
    secret = "session=offline-migration-cookie"
    assert (
        client.put(
            "/api/v1/settings", headers=auth, json={"platform_cookies": {"xiaoheihe": secret}}
        ).status_code
        == 200
    )
    with app.state.session_factory.begin() as db:
        db.add(Comment(note_id=note_id, content="升级前的评论", position=0, ai_score=0.9))
        encrypted = db.get(UserSettings, 1).platform_cookies["xiaoheihe"]
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    for _ in range(2):
        with app.state.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0015_summary_request_keys")
            assert "source_id" not in {
                column["name"] for column in inspect(connection).get_columns("comments")
            }
            assert (
                connection.scalar(
                    text("SELECT content FROM comments WHERE note_id=:id"), {"id": note_id}
                )
                == "升级前的评论"
            )
            command.upgrade(config, "head")
            command.check(config)
        note = client.get(f"/api/v1/notes/{note_id}", headers=auth).json()
        assert note["comment_insights"] == []
        assert note["comments"][0]["ai_score"] == 0.9
        assert note["comments"][0]["parent_source_id"] is None
        with app.state.session_factory() as db:
            stored = db.get(UserSettings, 1).platform_cookies["xiaoheihe"]
            assert stored == encrypted
            assert decrypt_secret(stored, app.state.settings) == secret
