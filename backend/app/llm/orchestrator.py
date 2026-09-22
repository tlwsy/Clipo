# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

from app.config import Settings
from app.extractors.base import CapturedContent
from app.llm.client import CompatibleClient
from app.llm.prompts import SYSTEM_PROMPT, truncate_text
from app.repositories import UserRepository
from app.security.credentials import decrypt_secret
from app.services.comments import select_comments
from app.services.settings import read_settings


class Summary(BaseModel):
    summary_markdown: str = Field(min_length=1, max_length=24000)
    key_points: list[str] = Field(max_length=20)
    suggested_tags: list[str] = Field(default_factory=list, max_length=10)


class CommentScore(BaseModel):
    index: int = Field(ge=0, strict=True)
    score: float = Field(ge=0, le=1, strict=True, allow_inf_nan=False)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class CommentScores(BaseModel):
    comment_scores: list[CommentScore] = Field(max_length=100)


@dataclass
class SummaryResult:
    summary: Summary | None
    error: str | None = None
    comment_scores: list[CommentScore] = field(default_factory=list)
    comment_score_threshold: float = 0.6
    comment_score_error: str | None = None


@dataclass
class LlmConfig:
    base_url: str
    model: str
    api_key: str
    token_budget: int
    max_comments: int = 30
    comment_score_threshold: float = 0.6


def load_config(repository: UserRepository, settings: Settings) -> LlmConfig:
    effective = read_settings(repository, settings).llm
    stored_key = repository.settings().llm_config.get("api_key")
    key = (
        settings.llm_api_key.get_secret_value()
        if settings.llm_api_key is not None
        else decrypt_secret(stored_key, settings) if stored_key else ""
    )
    return LlmConfig(
        effective.base_url,
        effective.model,
        key,
        effective.text_token_budget,
        effective.max_comments,
        effective.comment_score_threshold,
    )


def _decode_output(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Expected an object")
    return result


def _validate_summary(data: dict[str, Any]) -> Summary:
    result = Summary.model_validate(data)
    if not result.summary_markdown.strip() or any(
        not point.strip() or len(point) > 2000 for point in result.key_points
    ):
        raise ValueError("Empty summary or invalid key points")
    return result


def parse_summary(value: str) -> Summary:
    return _validate_summary(_decode_output(value))


def comment_payload(content: CapturedContent, limit: int) -> list[dict[str, Any]]:
    """Bound total serialized comment input to 8000 UTF-8 bytes, 1000 per text."""
    payload: list[dict[str, Any]] = []
    for position, comment in select_comments(content.comments, limit):
        candidate = {"index": position, "content": truncate_text(comment.content, 1000)}
        size = len(json.dumps([*payload, candidate], ensure_ascii=False).encode("utf-8"))
        if size > 8000:
            break
        payload.append(candidate)
    return payload


def _validate_scores(data: dict[str, Any], indices: set[int]) -> list[CommentScore]:
    scores = CommentScores.model_validate(data).comment_scores
    if len(scores) != len(indices) or {score.index for score in scores} != indices:
        raise ValueError("Scores must cover each candidate exactly once")
    return scores


def summarize(
    content: CapturedContent, config: LlmConfig, client: CompatibleClient | None = None
) -> SummaryResult:
    comments = comment_payload(content, config.max_comments)
    if not config.api_key:
        return SummaryResult(
            None,
            "未生成摘要：尚未配置模型密钥，可在设置中配置；原文已保存",
            comment_score_error=(
                "未生成评论评分：尚未配置模型密钥；已采集评论已保留" if comments else None
            ),
        )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "title": content.title[:1000],
                    "text": truncate_text(content.text, config.token_budget),
                    "comments": comments,
                },
                ensure_ascii=False,
            ),
        },
    ]
    client = client or CompatibleClient()
    last_summary = None
    for attempt in range(2):
        try:
            value = client.complete(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                messages=messages,
                json_mode=attempt == 0,
                max_tokens=2000 + 100 * len(comments),
            )
            data = _decode_output(value)
            last_summary = _validate_summary(data)
            scores = _validate_scores(data, {row["index"] for row in comments}) if comments else []
            return SummaryResult(
                last_summary,
                comment_scores=scores,
                comment_score_threshold=config.comment_score_threshold,
            )
        except Exception:
            # Provider bodies and exception strings may include credentials/content.
            pass
    score_error = (
        "未生成评论评分：模型服务不可用或评分格式无效；已采集评论已保留" if comments else None
    )
    if last_summary is not None:
        return SummaryResult(last_summary, comment_score_error=score_error)
    return SummaryResult(
        None,
        "未生成摘要：模型服务不可用或返回格式无效，请检查模型地址、密钥及额度；原文已保存",
        comment_score_error=score_error,
    )
