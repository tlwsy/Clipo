import json
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.extractors.base import CapturedContent
from app.llm.client import CompatibleClient
from app.llm.prompts import SYSTEM_PROMPT, truncate_text
from app.repositories import UserRepository
from app.security.credentials import decrypt_secret
from app.services.settings import read_settings


class Summary(BaseModel):
    summary_markdown: str = Field(min_length=1, max_length=24000)
    key_points: list[str] = Field(max_length=20)
    suggested_tags: list[str] = Field(default_factory=list, max_length=10)


@dataclass
class SummaryResult:
    summary: Summary | None
    error: str | None = None


@dataclass
class LlmConfig:
    base_url: str
    model: str
    api_key: str
    token_budget: int


def load_config(repository: UserRepository, settings: Settings) -> LlmConfig:
    effective = read_settings(repository, settings).llm
    stored_key = repository.settings().llm_config.get("api_key")
    key = (
        settings.llm_api_key.get_secret_value()
        if settings.llm_api_key is not None
        else decrypt_secret(stored_key, settings) if stored_key else ""
    )
    return LlmConfig(effective.base_url, effective.model, key, effective.text_token_budget)


def parse_summary(value: str) -> Summary:
    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    result = Summary.model_validate_json(text)
    if not result.summary_markdown.strip() or any(
        not point.strip() or len(point) > 2000 for point in result.key_points
    ):
        raise ValueError("Empty summary or invalid key points")
    return result


def summarize(
    content: CapturedContent, config: LlmConfig, client: CompatibleClient | None = None
) -> SummaryResult:
    if not config.api_key:
        return SummaryResult(None, "未生成摘要：尚未配置模型密钥，可在设置中配置；原文已保存")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "title": content.title[:1000],
                    "text": truncate_text(content.text, config.token_budget),
                },
                ensure_ascii=False,
            ),
        },
    ]
    client = client or CompatibleClient()
    for attempt in range(2):
        try:
            value = client.complete(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                messages=messages,
                json_mode=attempt == 0,
            )
            return SummaryResult(parse_summary(value))
        except (ValueError, ValidationError, KeyError, IndexError, TypeError):
            pass
        except Exception:
            # Provider bodies and exception strings may include credentials/content.
            pass
    return SummaryResult(
        None, "未生成摘要：模型服务不可用或返回格式无效，请检查模型地址、密钥及额度；原文已保存"
    )
