# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import json
import math
import time
from dataclasses import dataclass, field

import httpx

from app.config import Settings
from app.models import Note
from app.repositories import UserRepository
from app.security.credentials import decrypt_secret
from app.services.settings import read_settings

DIMENSIONS = 1536
EMBEDDING_ERROR = "向量生成失败，请检查嵌入模型、1536 维支持、密钥及额度后重试；原文和摘要已保留"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def note_input(note: Note) -> str:
    # Bound bytes, not just characters: multilingual input can consume many tokens.
    value = "\n\n".join([note.title, note.summary_markdown or "", *note.key_points]).strip()
    return value.encode()[:8000].decode("utf-8", errors="ignore") or "无标题笔记"


@dataclass(frozen=True)
class EmbeddingConfig:
    enabled: bool
    base_url: str
    model: str
    api_key: str = field(repr=False)

    @property
    def key(self) -> str:
        return digest(json.dumps([self.base_url.rstrip("/"), self.model, DIMENSIONS]))


def load_embedding_config(repository: UserRepository, settings: Settings) -> EmbeddingConfig:
    llm = read_settings(repository, settings).llm
    stored = repository.settings().llm_config.get("api_key")
    key = (
        settings.llm_api_key.get_secret_value()
        if settings.llm_api_key is not None
        else decrypt_secret(stored, settings) if stored else ""
    )
    return EmbeddingConfig(llm.embedding_enabled, llm.base_url, llm.embedding_model, key)


def validate_vector(value: object) -> list[float]:
    if not isinstance(value, list) or len(value) != DIMENSIONS:
        raise ValueError("Invalid embedding dimensions")
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in value):
        raise ValueError("Invalid embedding values")
    norm = math.hypot(*value)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Invalid embedding norm")
    # Normalize before float32 storage, avoiding overflow and consistent cosine semantics.
    return [float(item / norm) for item in value]


class EmbeddingClient:
    def embed(self, config: EmbeddingConfig, value: str) -> list[float]:
        started = time.monotonic()
        with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
            with client.stream(
                "POST",
                config.base_url.rstrip("/") + "/embeddings",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "input": value,
                    "encoding_format": "float",
                    "dimensions": DIMENSIONS,
                },
            ) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 256 * 1024 or time.monotonic() - started > 40:
                        raise ValueError("Embedding response limit exceeded")
        payload = json.loads(data)
        rows = payload["data"]
        if len(rows) != 1 or rows[0].get("index", 0) != 0:
            raise ValueError("Invalid embedding response")
        return validate_vector(rows[0]["embedding"])
