import json
from typing import Any

import pytest
from app.extractors.base import CapturedComment, CapturedContent
from app.extractors.registry import ExtractorRegistry
from app.models import ExtractionCache, Note, UserSettings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.conftest import ACCOUNT

CONTENT = CapturedContent(
    url="https://example.com/comments",
    title="评论集成测试",
    text="用于评分的正文",
    comments=[
        CapturedComment(content="最低点赞的具体建议", likes=1),
        CapturedComment(content="重复评论需要保留原始内容", likes=2),
        CapturedComment(content="另一条有具体操作的评论", likes=20),
        CapturedComment(content="重复评论需要保留原始内容", likes=30),
        CapturedComment(content="谢谢", likes=100),
        CapturedComment(content="👍👍👍👍👍", likes=200),
    ],
)


class Extractor:
    name = "fixture"

    def __init__(self) -> None:
        self.calls = 0

    def matches(self, url: str) -> bool:
        return True

    def extract(self, url: str, payload: dict | None = None) -> CapturedContent:
        self.calls += 1
        return CONTENT.model_copy(deep=True)


class Model:
    def __init__(self, invalid: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.invalid = invalid

    def complete(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        comments = json.loads(kwargs["messages"][1]["content"])["comments"]
        return json.dumps(
            {
                "summary_markdown": "有效摘要",
                "key_points": ["有效要点"],
                "comment_scores": (
                    []
                    if self.invalid
                    else [
                        {
                            "index": row["index"],
                            "score": 0.6 if row["index"] == 3 else 0.4,
                            "reason": f"第 {row['index']} 条评分依据",
                        }
                        for row in reversed(comments)
                    ]
                ),
            }
        )


@pytest.fixture
def scoring(app: FastAPI) -> tuple[Extractor, Model]:
    extractor, model = Extractor(), Model()
    app.state.capture_queue.pipeline.registry = ExtractorRegistry([extractor])
    app.state.capture_queue.pipeline.llm = model
    return extractor, model


def capture(client: TestClient, app: FastAPI, auth: dict[str, str]) -> dict[str, Any]:
    response = client.post("/api/v1/captures", headers=auth, json={"url": CONTENT.url})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    huey = app.state.capture_queue.huey
    huey.execute(huey.dequeue())
    job = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()
    assert job["status"] == "success", job
    return client.get(f"/api/v1/notes/{job['note_id']}", headers=auth).json()


def test_scores_map_to_original_comments_and_cache_is_rescored_with_current_settings(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    scoring: tuple[Extractor, Model],
) -> None:
    extractor, model = scoring
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "llm": {
                "api_key": "private-key",
                "max_comments": 2,
                "comment_score_threshold": 0.6,
            }
        },
    )
    note = capture(client, app, auth)
    assert note["status"] == "ready" and note["comment_score_error"] is None
    assert note["content"]["comments"] == CONTENT.model_dump(mode="json")["comments"]
    assert len(note["comments"]) == 6
    assert [row["ai_score"] for row in note["comments"]] == [None, None, 0.4, 0.6, None, None]
    assert [row["is_valuable"] for row in note["comments"]] == [
        False,
        False,
        False,
        True,
        False,
        False,
    ]
    assert note["comments"][3]["ai_reason"] == "第 3 条评分依据"
    assert len(model.calls) == 1
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "llm": {
                "max_comments": 1,
                "comment_score_threshold": 0.7,
            }
        },
    )
    next_note = capture(client, app, auth)
    assert extractor.calls == 1 and len(model.calls) == 2
    assert [row["ai_score"] for row in next_note["comments"]] == [None, None, None, 0.6, None, None]
    assert not any(row["is_valuable"] for row in next_note["comments"])
    old = client.get(f"/api/v1/notes/{note['id']}", headers=auth).json()
    assert old["comments"][3]["is_valuable"] is True
    with app.state.session_factory() as db:
        assert "ai_score" not in db.scalar(select(ExtractionCache)).content["comments"][3]
        assert db.get(Note, note["id"]).comment_score_error is None


def test_invalid_scoring_keeps_summary_and_all_comments_unscored(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    scoring: tuple[Extractor, Model],
) -> None:
    scoring[1].invalid = True
    client.put("/api/v1/settings", headers=auth, json={"llm": {"api_key": "private-key"}})
    note = capture(client, app, auth)
    assert note["status"] == "ready" and note["summary_markdown"] == "有效摘要"
    assert note["summary_error"] is None
    assert "评分格式无效" in note["comment_score_error"]
    assert len(note["comments"]) == 6
    assert all(row["ai_score"] is None and not row["is_valuable"] for row in note["comments"])
    assert len(scoring[1].calls) == 2


@pytest.mark.parametrize("corrupt", [False, True])
def test_missing_or_corrupt_model_key_saves_original_comments_without_scores(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    scoring: tuple[Extractor, Model],
    corrupt: bool,
) -> None:
    if corrupt:
        with app.state.session_factory.begin() as db:
            db.get(UserSettings, 1).llm_config = {"api_key": "corrupt-private-value"}
    note = capture(client, app, auth)
    assert note["status"] == "original_only"
    assert note["content"]["text"] == CONTENT.text and len(note["comments"]) == 6
    assert all(row["ai_score"] is None and row["ai_reason"] is None for row in note["comments"])
    assert "未生成评论评分" in note["comment_score_error"]
    assert "private" not in json.dumps(note)
    assert scoring[1].calls == []


def test_comment_settings_and_scored_notes_are_scoped_to_each_account(
    client: TestClient,
    app: FastAPI,
    auth: dict[str, str],
    scoring: tuple[Extractor, Model],
) -> None:
    app.state.settings.registration_open = True
    second = client.post(
        "/api/v1/auth/register",
        json={
            **ACCOUNT,
            "username": "second",
            "email": "second@example.com",
        },
    ).json()
    other = {"Authorization": "Bearer " + second["access_token"]}
    client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "llm": {
                "api_key": "first-key",
                "max_comments": 1,
                "comment_score_threshold": 0.6,
            }
        },
    )
    client.put(
        "/api/v1/settings",
        headers=other,
        json={
            "llm": {
                "api_key": "second-key",
                "max_comments": 3,
                "comment_score_threshold": 0.8,
            }
        },
    )
    first, second_note = capture(client, app, auth), capture(client, app, other)
    assert first["comments"][3]["is_valuable"]
    assert not any(row["is_valuable"] for row in second_note["comments"])
    assert sum(row["ai_score"] is not None for row in first["comments"]) == 1
    assert sum(row["ai_score"] is not None for row in second_note["comments"]) == 3
    assert [call["api_key"] for call in scoring[1].calls] == ["first-key", "second-key"]
    assert scoring[0].calls == 2
    assert client.get(f"/api/v1/notes/{first['id']}", headers=other).status_code == 404


@pytest.mark.parametrize(
    "settings",
    [
        {"max_comments": 0},
        {"max_comments": 101},
        {"max_comments": 1.5},
        {"comment_score_threshold": -0.1},
        {"comment_score_threshold": 1.01},
    ],
)
def test_invalid_comment_settings_do_not_partially_update(
    client: TestClient,
    auth: dict[str, str],
    settings: dict[str, float],
) -> None:
    response = client.put(
        "/api/v1/settings",
        headers=auth,
        json={
            "llm": {**settings, "model": "must-not-save"},
        },
    )
    assert response.status_code == 422
    assert client.get("/api/v1/settings", headers=auth).json()["llm"]["model"] == "qwen-plus"
