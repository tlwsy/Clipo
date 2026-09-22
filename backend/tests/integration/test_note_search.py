# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT
from app.extractors.base import CapturedContent
from app.models import Note
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_note_organization import seed_note


@pytest.fixture
def searchable(app: FastAPI, auth: dict) -> tuple[int, int, int]:
    ids = tuple(seed_note(app) for _ in range(3))
    with app.state.session_factory.begin() as db:
        for note_id, title, body, summary in zip(
            ids,
            ["中文标题测试", "其他笔记", "其他笔记"],
            ["只有原文内容，OpenAI API 100%_literal", "中文标题测试在正文中", "空白正文"],
            ["摘要关键词适配器", None, "中文标题测试在摘要中"],
            strict=True,
        ):
            note = db.get(Note, note_id)
            note.title = title
            note.content = CapturedContent(
                url=note.url, title=title, text=body, raw_html="只在快照出现的秘密"
            ).model_dump(mode="json")
            note.summary_markdown = summary
    return ids


def search(client: TestClient, auth: dict, query: str, **params: object) -> dict:
    response = client.get("/api/v1/notes", headers=auth, params={"q": query, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_chinese_hits_title_body_summary_and_paginates(
    client: TestClient, auth: dict, searchable: tuple[int, ...]
) -> None:
    for term in ("中文标题测试", "文标题", "标题", "标"):
        assert {row["id"] for row in search(client, auth, term)["items"]} == set(searchable)
    first = search(client, auth, "标题", limit=2)
    second = search(client, auth, "标题", limit=2, cursor=first["next_cursor"])
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert {row["id"] for row in search(client, auth, "\u3000  ")["items"]} == set(searchable)


@pytest.mark.parametrize(
    "term,count",
    [
        ("中文 适配器", 1),
        ("OpenAI api", 1),
        ("100%_literal", 1),
        ("不存在的内容", 0),
        ("%", 1),
        ("_", 1),
        ('" OR 1=1 --', 0),
        ("* NEAR(title)", 0),
        ("只在快照出现的秘密", 0),
    ],
)
def test_literal_query_and_multiword_terms(
    client: TestClient, auth: dict, searchable: tuple[int, ...], term: str, count: int
) -> None:
    assert len(search(client, auth, term)["items"]) == count


def test_search_combines_filters_and_cannot_read_other_users(
    app: FastAPI, client: TestClient, auth: dict, searchable: tuple[int, ...]
) -> None:
    note_id = searchable[0]
    tag = client.post(f"/api/v1/notes/{note_id}/tags", headers=auth, json={"name": "检索"}).json()
    client.patch(f"/api/v1/notes/{note_id}", headers=auth, json={"is_favorite": True})
    assert [
        row["id"] for row in search(client, auth, "中文", tag_id=tag["id"], favorite=True)["items"]
    ] == [note_id]
    app.state.settings.registration_open = True
    session = client.post(
        "/api/v1/auth/register",
        json={
            "username": "searcher",
            "email": "searcher@example.com",
            "password": "search-test-password",
        },
    ).json()
    other = {"Authorization": "Bearer " + session["access_token"]}
    assert search(client, other, "中文")["items"] == []
    assert search(client, other, "中文", tag_id=tag["id"])["items"] == []
    client.delete(f"/api/v1/notes/{note_id}", headers=auth)
    assert search(client, auth, "适配器")["items"] == []
    assert len(search(client, auth, "中文")["items"]) == 2


def test_search_migration_backfill_and_rollback(
    app: FastAPI, client: TestClient, auth: dict, searchable: tuple[int, ...]
) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006_note_organization")
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
    assert len(search(client, auth, "中文")["items"]) == 3
    mode = client.get("/api/v1/meta/capabilities", headers=auth).json()["fulltext_search"]
    assert mode in {"sqlite_fts5", "postgresql_tsvector_like", "postgresql_bigm"}
    assert client.get("/api/v1/notes", headers=auth, params={"q": "x" * 201}).status_code == 422
