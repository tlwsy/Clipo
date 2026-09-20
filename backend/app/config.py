from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLIPO_",
        env_file=BACKEND_ROOT.parent / ".env",
        extra="ignore",
    )

    secret_key: SecretStr
    base_url: str = "http://localhost:8000"
    database_url: str = f"sqlite:///{BACKEND_ROOT.parent / 'data' / 'clipo.db'}"
    db_pool_size: int = 5
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    registration_open: bool = False
    timezone: str = "Asia/Shanghai"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_days: int = 30
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    static_path: Path = BACKEND_ROOT / "app" / "static"
    queue_path: Path = BACKEND_ROOT.parent / "data" / "huey.db"
    extraction_cache_ttl_seconds: int = Field(default=86400, ge=0, le=2592000)

    @field_validator("secret_key")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or secret.startswith("change-me"):
            raise ValueError(
                "CLIPO_SECRET_KEY 至少需要 32 个字符，请使用 openssl rand -hex 32 生成"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
