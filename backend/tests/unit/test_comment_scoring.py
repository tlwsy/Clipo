import json
from typing import Any

import pytest
from app.extractors.base import CapturedComment, CapturedContent
from app.llm.orchestrator import LlmConfig, comment_payload, summarize

CONTENT = CapturedContent(
    url="https://example.com",
    title="评论评分",
    text="正文内容不应被评论替换。",
    comments=[
        CapturedComment(content="谢谢", likes=100),
        CapturedComment(content="建议保存完整的原文", likes=4),
        CapturedComment(content="补充一个具体操作步骤", likes=20),
    ],
)
CONFIG = LlmConfig("https://model.example/v1", "test", "private-key", 1000)
SUMMARY = {"summary_markdown": "仅依据正文的摘要", "key_points": ["正文要点"]}
SCORES = [
    {"index": 1, "score": 0.6, "reason": "补充建议"},
    {"index": 2, "score": 0.9, "reason": "提供具体步骤"},
]


class Model:
    def __init__(self, values: list[dict[str, Any] | str | Exception]) -> None:
        self.values = iter(values)
        self.calls: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value


def test_summary_and_scores_share_one_call_and_use_original_indices() -> None:
    model = Model([{**SUMMARY, "comment_scores": SCORES}])
    result = summarize(CONTENT, CONFIG, model)
    assert result.summary.summary_markdown == SUMMARY["summary_markdown"]
    assert [score.index for score in result.comment_scores] == [1, 2]
    assert result.comment_score_threshold == 0.6
    assert result.comment_score_error is None
    assert len(model.calls) == 1
    payload = json.loads(model.calls[0]["messages"][1]["content"])
    assert [row["index"] for row in payload["comments"]] == [2, 1]
    assert payload["text"] == CONTENT.text
    assert model.calls[0]["max_tokens"] == 2200


def test_comment_prompt_has_a_total_budget_and_per_comment_limit_without_mutating_source() -> None:
    content = CONTENT.model_copy(
        update={
            "comments": [
                CapturedComment(content=f"详细建议{index}" + "中文🙂" * 1000)
                for index in range(100)
            ]
        }
    )
    payload = comment_payload(content, 100)
    assert 1 <= len(payload) < 100
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= 8000
    assert all(len(row["content"].encode("utf-8")) <= 1000 for row in payload)
    assert len(content.comments[0].content) > 1000
    assert len(content.comments) == 100


@pytest.mark.parametrize(
    "bad_scores",
    [
        None,
        [],
        [SCORES[0]],
        [SCORES[0], SCORES[0]],
        [SCORES[0], {**SCORES[1], "index": 0}],
        [SCORES[0], {**SCORES[1], "index": 20}],
        [SCORES[0], {**SCORES[1], "index": "2"}],
        [SCORES[0], {**SCORES[1], "index": 2.0}],
        [{**SCORES[0], "index": True}, SCORES[1]],
        [SCORES[0], {**SCORES[1], "score": 1.1}],
        [SCORES[0], {**SCORES[1], "score": -0.1}],
        [SCORES[0], {**SCORES[1], "score": "0.9"}],
        [SCORES[0], {**SCORES[1], "score": True}],
        [SCORES[0], {**SCORES[1], "score": float("nan")}],
        [SCORES[0], {**SCORES[1], "score": float("inf")}],
        [SCORES[0], {**SCORES[1], "reason": "   "}],
        [SCORES[0], {**SCORES[1], "reason": "x" * 301}],
    ],
)
def test_invalid_scores_retry_without_mislabeling_or_losing_valid_summary(bad_scores: Any) -> None:
    model = Model([{**SUMMARY, "comment_scores": bad_scores}, RuntimeError("private-key response")])
    result = summarize(CONTENT, CONFIG, model)
    assert len(model.calls) == 2
    assert model.calls[1]["json_mode"] is False
    assert result.summary.summary_markdown == SUMMARY["summary_markdown"]
    assert result.error is None and result.comment_scores == []
    assert "评分格式无效" in result.comment_score_error
    assert "private" not in result.comment_score_error


def test_valid_retry_recovers_scores() -> None:
    model = Model([{**SUMMARY}, {**SUMMARY, "comment_scores": SCORES}])
    result = summarize(CONTENT, CONFIG, model)
    assert result.comment_score_error is None
    assert len(result.comment_scores) == 2


def test_model_and_key_failures_preserve_unscored_comments() -> None:
    model = Model([RuntimeError("private-key response"), "invalid-json"])
    result = summarize(CONTENT, CONFIG, model)
    assert result.summary is None and result.comment_scores == []
    assert "原文已保存" in result.error
    assert "已采集评论已保留" in result.comment_score_error
    missing_key = LlmConfig("", "", "", 1000)
    model = Model([])
    result = summarize(CONTENT, missing_key, model)
    assert "尚未配置" in result.comment_score_error
    assert model.calls == []


def test_absent_candidates_ignore_unsolicited_scores_and_require_no_scoring_fields() -> None:
    content = CONTENT.model_copy(update={"comments": [CONTENT.comments[0]]})
    model = Model([{**SUMMARY, "comment_scores": [{"index": 0, "score": 1, "reason": "fake"}]}])
    result = summarize(content, CONFIG, model)
    assert result.comment_scores == [] and result.comment_score_error is None
    assert json.loads(model.calls[0]["messages"][1]["content"])["comments"] == []
    assert model.calls[0]["max_tokens"] == 2000
