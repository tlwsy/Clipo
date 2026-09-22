# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import pytest
from app.extractors.base import CapturedContent
from app.llm.orchestrator import LlmConfig, parse_summary, summarize
from app.llm.prompts import truncate_text

CONTENT = CapturedContent(url="https://example.com", title="测试", text="长篇中文正文" * 100)
CONFIG = LlmConfig("https://model.example/v1", "test", "secret-key", 100)
OUTPUT = {
    "summary_markdown": "## 摘要\n保留原文",
    "key_points": ["保存来源"],
    "suggested_tags": ["阅读"],
}


class StubModel:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.values)
        if isinstance(result, Exception):
            raise result
        return result


def test_budget_is_safe_for_chinese_and_emoji():
    original = "中文🙂hello" * 100
    result = truncate_text(original, 103)
    assert original.startswith(result)
    assert len(result.encode("utf-8")) <= 103


def test_structured_output_retries_invalid_json_without_echoing_it():
    client = StubModel(["not-json", json.dumps(OUTPUT)])
    result = summarize(CONTENT, CONFIG, client)
    assert result.summary.key_points == ["保存来源"]
    assert len(client.calls) == 2
    assert client.calls[0]["json_mode"] is True
    assert client.calls[1]["json_mode"] is False
    assert len(json.loads(client.calls[0]["messages"][1]["content"])["text"].encode()) <= 100


def test_model_failure_downgrades_and_redacts_secrets():
    client = StubModel([RuntimeError("secret-key provider body")] * 2)
    result = summarize(CONTENT, CONFIG, client)
    assert result.summary is None
    assert "原文已保存" in result.error
    assert "secret-key" not in result.error


def test_no_key_never_calls_model():
    client = StubModel([])
    result = summarize(CONTENT, LlmConfig("", "", "", 100), client)
    assert result.summary is None
    assert "尚未配置" in result.error
    assert not client.calls


def test_accepts_fenced_json_from_compatible_models():
    assert parse_summary("```json\n" + json.dumps(OUTPUT) + "\n```").suggested_tags == ["阅读"]


def test_compatible_http_client_sends_expected_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from app.llm.client import CompatibleClient

    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(OUTPUT)}}]})

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )
    content = CompatibleClient().complete(
        base_url="https://model.example/v1/",
        api_key="test-key",
        model="test-model",
        messages=[{"role": "user", "content": "text"}],
        max_tokens=2400,
    )
    assert parse_summary(content).key_points == ["保存来源"]
    request = requests[0]
    assert request.url == "https://model.example/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    assert json.loads(request.content)["response_format"] == {"type": "json_object"}
    assert json.loads(request.content)["max_tokens"] == 2400
