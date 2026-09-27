# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import time
from pathlib import Path
from typing import Any

import pytest
from app.extractors.base import CapturedComment, CapturedContent, ExtractionError
from app.extractors.bilibili import BilibiliExtractor
from app.extractors.generic import PlatformRequests
from app.extractors.xhs_api import XhsClient
from app.extractors.xiaoheihe import _append_comments
from app.extractors.xiaohongshu import XiaohongshuExtractor, parse_xiaohongshu
from app.extractors.youtube import YoutubeExtractor
from app.llm.orchestrator import comment_payload, summarize
from pydantic import SecretStr
from tests.unit.test_comment_scoring import CONFIG, CONTENT, SCORES, SUMMARY, Model

FIXTURES = Path(__file__).parents[1] / "fixtures"


def content() -> CapturedContent:
    return CapturedContent(url="https://example.com", title="回复", text="正文")


def test_html_replies_keep_relationships_deduplicate_and_share_limit() -> None:
    html = (FIXTURES / "comment-threads.html").read_text()
    note = parse_xiaohongshu(html, "https://www.xiaohongshu.com/explore/thread1")
    assert [(row.source_id, row.parent_source_id) for row in note.comments] == [
        ("root", None),
        ("reply", "root"),
        ("nested", "reply"),
        ("other", None),
    ]
    limited = parse_xiaohongshu(html, note.url, max_comments=2)
    assert [row.source_id for row in limited.comments] == ["root", "reply"]
    assert parse_xiaohongshu(html, note.url, max_comments=0).comments == []


def test_xhs_reply_pagination_keeps_prior_results_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [{"id": "root", "content": "主评论内容", "sub_comment_count": 3}]
    note = content()
    calls = []

    def replies(self: object, *args: str) -> dict[str, Any]:
        calls.append(args)
        if len(calls) == 2:
            raise ExtractionError("private response")
        return {
            "comments": [{"id": "reply", "content": "回复补充操作步骤"}],
            "has_more": True,
            "cursor": "next",
        }

    monkeypatch.setattr(XhsClient, "replies", replies)
    XiaohongshuExtractor().collect_replies(
        note, rows, XhsClient(SecretStr("a1=offline")), "note", "token", time.monotonic() + 10
    )
    assert [row.source_id for row in note.comments] == ["root", "reply"]
    assert note.comments[1].parent_source_id == "root"
    assert calls[1][-1] == "next"
    assert note.capture_warnings and "private" not in str(note.capture_warnings)


def test_heybox_keeps_entire_floor_and_limit() -> None:
    note = content()
    data = {
        "comments": [
            {
                "comment": [
                    {"commentid": 1, "text": "主评论内容"},
                    {"commentid": 2, "text": "楼中楼的具体建议"},
                    {"commentid": 3, "text": "更多回复内容"},
                ]
            }
        ]
    }
    _append_comments(note, data, set(), 2)
    assert [(row.source_id, row.parent_source_id) for row in note.comments] == [
        ("1", None),
        ("2", "1"),
    ]


def test_heybox_nested_children_are_deduplicated_against_floor_entries() -> None:
    note = content()
    child = {"commentid": 2, "text": "嵌套回复内容"}
    data = {
        "comments": [{"comment": [{"commentid": 1, "text": "根评论", "children": [child]}, child]}]
    }
    _append_comments(note, data, set(), 100)
    assert [(row.source_id, row.parent_source_id) for row in note.comments] == [
        ("1", None),
        ("2", "1"),
    ]


def test_bili_fetches_replies_before_next_top_level_page(monkeypatch: pytest.MonkeyPatch) -> None:
    note = content()
    calls = []

    def api(self: object, path: str, params: dict[str, str], requests: object) -> dict[str, Any]:
        calls.append(path)
        if path == "/x/v2/reply":
            return {
                "replies": [
                    {"rpid": i, "rcount": 1, "content": {"message": f"主评论{i}"}}
                    for i in range(1, 21)
                ]
            }
        return {"replies": [{"rpid": 99, "content": {"message": "回复补充内容"}}]}

    monkeypatch.setattr(BilibiliExtractor, "api", api)
    BilibiliExtractor(max_comments=21).comments(note, "42", PlatformRequests())
    assert calls == ["/x/v2/reply", "/x/v2/reply/reply"]
    assert len(note.comments) == 21
    assert note.comments[-1].parent_source_id == "1"


def test_bili_embedded_and_paginated_replies(monkeypatch: pytest.MonkeyPatch) -> None:
    note = content()
    calls = []

    def api(self: object, path: str, params: dict[str, str], requests: object) -> dict[str, Any]:
        calls.append(path)
        reply = {"rpid": 2, "parent": 1, "content": {"message": "回复的具体经验"}}
        if path == "/x/v2/reply":
            return {
                "replies": [
                    {
                        "rpid": 1,
                        "rcount": 2,
                        "content": {"message": "主评论内容"},
                        "replies": [reply],
                    }
                ]
            }
        return {"replies": [reply, {"rpid": 3, "parent": 2, "content": {"message": "回复的回复"}}]}

    monkeypatch.setattr(BilibiliExtractor, "api", api)
    BilibiliExtractor().comments(note, "42", PlatformRequests())
    assert [(row.source_id, row.parent_source_id) for row in note.comments] == [
        ("1", None),
        ("2", "1"),
        ("3", "2"),
    ]
    assert calls == ["/x/v2/reply", "/x/v2/reply/reply"]


def test_youtube_reply_continuation_preserves_parent_and_bounds_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = content()
    calls = []

    def next_page(self: object, token: str, config: dict, requests: object) -> dict:
        calls.append(token)
        return {
            "commentRenderer": {"commentId": "child", "contentText": {"simpleText": "reply"}},
            "continuationItemRenderer": {
                "continuationEndpoint": {"continuationCommand": {"token": token}}
            },
        }

    monkeypatch.setattr(YoutubeExtractor, "next_page", next_page)
    YoutubeExtractor().collect_replies(
        note, [("root", "cursor")], {}, PlatformRequests(), set(), time.monotonic() + 10
    )
    assert calls == ["cursor"]
    assert note.comments[0].parent_source_id == "root"


def test_insights_only_reference_valuable_scored_comments() -> None:
    model = Model(
        [
            {
                **SUMMARY,
                "comment_scores": SCORES,
                "comment_insights": [
                    {"text": "合并具体操作建议", "indices": [1, 2]},
                    {"text": "不应引用未评分评论", "indices": [0]},
                    {"text": "不应引用不存在评论", "indices": [99]},
                    {"text": " ", "indices": [1]},
                ],
            }
        ]
    )
    result = summarize(CONTENT, CONFIG, model)
    assert [row.text for row in result.comment_insights] == ["合并具体操作建议"]
    payload = json.loads(model.calls[0]["messages"][1]["content"])
    assert payload["comment_score_threshold"] == CONFIG.comment_score_threshold
    assert len(model.calls) == 1


def test_reply_scoring_includes_bounded_context_without_scoring_parent() -> None:
    note = content()
    note.comments = [
        CapturedComment(source_id="root", content="问题？"),
        CapturedComment(
            source_id="reply", parent_source_id="root", content="请使用完整链接保存笔记"
        ),
    ]
    payload = comment_payload(note, 10)
    assert len(payload) == 1 and payload[0]["index"] == 1
    assert payload[0]["parent_context"] == "问题？"
