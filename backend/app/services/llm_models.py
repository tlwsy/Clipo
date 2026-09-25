# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read an unsaved or configured provider's model catalog without persisting credentials."""

import json
import time
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.errors import ClipoError
from app.extractors.base import ExtractionError
from app.repositories import UserRepository
from app.schemas.settings import LlmModelsRequest
from app.security.credentials import decrypt_secret
from app.security.urls import normalize_url, public_addresses
from app.services.settings import read_settings


def discover_models(
    repository: UserRepository, settings: Settings, payload: LlmModelsRequest
) -> list[str]:
    current = read_settings(repository, settings).llm
    base_url = (
        str(payload.base_url)
        if payload.base_url is not None and "base_url" not in current.overridden_fields
        else current.base_url
    ).rstrip("/")
    changed = base_url != current.base_url.rstrip("/")
    if changed and ("api_key" not in payload.model_fields_set or settings.llm_api_key is not None):
        raise ClipoError(422, "llm_key_required", "更换服务地址后，请填写该服务的 API Key")
    if settings.llm_api_key is not None:
        key = settings.llm_api_key.get_secret_value()
    elif "api_key" in payload.model_fields_set:
        key = payload.api_key.get_secret_value() if payload.api_key else ""
    else:
        stored = repository.settings().llm_config.get("api_key")
        try:
            key = decrypt_secret(stored, settings) if stored else ""
        except Exception:
            raise ClipoError(422, "llm_key_invalid", "密钥无法读取，请重新填写 API Key") from None
    if not key:
        raise ClipoError(422, "llm_key_required", "请先填写 API Key，再获取模型列表")
    try:
        url = normalize_url(base_url)
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.query or parts.fragment:
            raise ClipoError(
                422, "llm_url_invalid", "获取模型列表需要不含查询参数的公开 HTTPS 地址"
            )
        addresses = public_addresses(url)
        url = url.rstrip("/") + "/models"
        started = time.monotonic()
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
            with client.stream(
                "GET",
                httpx.URL(url).copy_with(host=addresses[0]),
                headers={
                    "Authorization": f"Bearer {key}",
                    "Host": parts.netloc,
                    "Accept": "application/json",
                },
                extensions={"sni_hostname": parts.hostname},
            ) as response:
                if response.status_code in (401, 403):
                    raise ClipoError(
                        422, "llm_key_rejected", "服务未接受此密钥，请检查 API Key 与权限"
                    )
                if response.status_code in (404, 405):
                    raise ClipoError(
                        422, "llm_models_unsupported", "服务不支持获取模型列表，请手动填写模型名称"
                    )
                response.raise_for_status()
                if "json" not in response.headers.get("content-type", "").lower():
                    raise ValueError()
                data = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    data.extend(chunk)
                    if len(data) > 4 * 1024 * 1024 or time.monotonic() - started > 20:
                        raise ValueError()
        catalog = json.loads(data)
        rows = catalog.get("data") if isinstance(catalog, dict) else None
        if not isinstance(rows, list):
            raise ValueError()
        models = set()
        for row in rows:
            identifier = row.get("id") if isinstance(row, dict) else None
            if (
                isinstance(identifier, str)
                and 0 < len(identifier.strip()) <= 100
                and all(ord(char) >= 32 and ord(char) != 127 for char in identifier)
                and key not in identifier
            ):
                models.add(identifier.strip())
        if len(models) > 5000:
            raise ValueError()
        return sorted(models, key=str.casefold)
    except ExtractionError:
        raise ClipoError(
            422, "llm_url_invalid", "无法访问此地址，请使用可解析的公开 HTTPS 模型服务地址"
        ) from None
    except (httpx.HTTPError, ValueError, UnicodeError):
        raise ClipoError(
            502,
            "llm_models_unavailable",
            "暂时无法获取模型列表，请检查地址或稍后重试，也可手动填写",
        ) from None
