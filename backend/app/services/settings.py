from typing import Any

from app.config import Settings
from app.repositories import UserRepository
from app.schemas.settings import LlmResponse, LlmUpdate, SettingsResponse
from app.security.credentials import encrypt_secret

LLM_DEFAULTS: dict[str, Any] = {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-plus",
    "comment_score_threshold": 0.6,
    "max_comments": 30,
    "text_token_budget": 8000,
}


def read_settings(repository: UserRepository, settings: Settings) -> SettingsResponse:
    stored = repository.settings().llm_config
    effective = {
        **LLM_DEFAULTS,
        **{key: value for key, value in stored.items() if key != "api_key"},
    }
    overrides = []
    for key in ("base_url", "model"):
        value = getattr(settings, f"llm_{key}")
        if value is not None:
            effective[key] = value
            overrides.append(key)
    if settings.llm_api_key is not None:
        api_key_set = bool(settings.llm_api_key.get_secret_value())
        overrides.append("api_key")
    else:
        api_key_set = bool(stored.get("api_key"))
    return SettingsResponse(
        llm=LlmResponse(**effective, api_key_set=api_key_set, overridden_fields=overrides)
    )


def update_llm(repository: UserRepository, payload: LlmUpdate, settings: Settings) -> None:
    config = dict(repository.settings().llm_config)
    for key in payload.model_fields_set:
        value = getattr(payload, key)
        if value is None:
            config.pop(key, None)
        elif key == "api_key":
            secret = value.get_secret_value()
            if secret:
                config[key] = encrypt_secret(secret, settings)
            else:
                config.pop(key, None)
        else:
            config[key] = str(value) if key == "base_url" else value
    repository.set_llm(config)
