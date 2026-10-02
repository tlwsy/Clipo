# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import math

import httpx
import pytest
from app.models import Note
from app.services.embeddings import (
    DIMENSIONS,
    EmbeddingClient,
    EmbeddingConfig,
    note_input,
    validate_vector,
)
from app.services.semantic_search import choose_mode


@pytest.mark.parametrize(
    "value",
    [
        [],
        [1] * 3,
        [0] * DIMENSIONS,
        [float("nan")] * DIMENSIONS,
        [float("inf")] * DIMENSIONS,
        ["1"] * DIMENSIONS,
        [True] * DIMENSIONS,
    ],
)
def test_reject_invalid_vectors(value: object) -> None:
    with pytest.raises(ValueError):
        validate_vector(value)


def test_embedding_client_contract_and_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [2.0] * DIMENSIONS}]})

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )
    config = EmbeddingConfig(True, "https://model.example/v1/", "embeddings-test", "secret")
    result = EmbeddingClient().embed(config, "中文查询")
    assert math.hypot(*result) == pytest.approx(1)
    assert requests[0].url == "https://model.example/v1/embeddings"
    assert json.loads(requests[0].content) == {
        "model": "embeddings-test",
        "input": "中文查询",
        "dimensions": 1536,
        "encoding_format": "float",
    }
    assert "secret" not in repr(config)


@pytest.mark.parametrize(
    "status,payload",
    [
        (302, {}),
        (401, {"error": "secret"}),
        (200, {"data": []}),
        (200, {"data": [{"embedding": [1] * DIMENSIONS, "index": 1}]}),
        (200, {"data": [{"embedding": [1] * DIMENSIONS}] * 2}),
        (200, {"data": [{"embedding": [1] * DIMENSIONS}], "padding": "x" * 262144}),
    ],
)
def test_embedding_http_failures_are_bounded(
    monkeypatch: pytest.MonkeyPatch, status: int, payload: dict
) -> None:
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload)),
            **kwargs,
        ),
    )
    with pytest.raises((ValueError, httpx.HTTPError)):
        EmbeddingClient().embed(
            EmbeddingConfig(True, "https://model.example/v1", "test", "key"), "q"
        )


def test_input_bounds_and_auto_modes() -> None:
    note = Note(title="中文😀" * 2000, summary_markdown="摘要", key_points=["要点"])
    assert len(note_input(note).encode()) <= 8000
    assert choose_mode("深度工作", "auto") == "fulltext"
    assert choose_mode('"深度工作和专注力之间的关系"', "auto") == "fulltext"
    assert choose_mode("深度工作和专注力之间的关系", "auto") == "semantic"
    assert choose_mode("how to focus", "auto") == "semantic"
    assert choose_mode("anything", "semantic") == "semantic"
    assert choose_mode("怎么提升专注力", "fulltext") == "fulltext"
