import re
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    StringConstraints,
    field_validator,
)


class LlmUpdate(BaseModel):
    base_url: HttpUrl | None = None
    model: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    comment_score_threshold: float | None = Field(default=None, ge=0, le=1)
    max_comments: int | None = Field(default=None, ge=1, le=100)
    text_token_budget: int | None = Field(default=None, ge=100, le=100000)


class PlatformCookiesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    xiaohongshu: SecretStr | None = Field(default=None, max_length=16384)
    xiaoheihe: SecretStr | None = Field(default=None, max_length=16384)

    @field_validator("xiaohongshu", "xiaoheihe")
    @classmethod
    def validate_cookie(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or value.get_secret_value() == "":
            return value
        cookie = value.get_secret_value()
        if any(ord(char) < 32 or ord(char) > 126 for char in cookie):
            raise ValueError("Cookie must contain only printable ASCII characters")
        cookie = cookie.strip()
        for pair in cookie.split(";"):
            name, separator, _ = pair.strip().partition("=")
            if not separator or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
                raise ValueError("Expected a Cookie request header value")
        return SecretStr(cookie)


class SettingsUpdate(BaseModel):
    llm: LlmUpdate | None = None
    platform_cookies: PlatformCookiesUpdate | None = None


class LlmResponse(BaseModel):
    base_url: str
    model: str
    api_key_set: bool
    comment_score_threshold: float
    max_comments: int
    text_token_budget: int
    overridden_fields: list[str]


class PlatformCookieStatus(BaseModel):
    cookie_set: bool


class PlatformCookiesResponse(BaseModel):
    xiaohongshu: PlatformCookieStatus
    xiaoheihe: PlatformCookieStatus


class SettingsResponse(BaseModel):
    llm: LlmResponse
    platform_cookies: PlatformCookiesResponse


class VersionResponse(BaseModel):
    version: str
    api_version: str = "v1"
    setup_completed: bool
    registration_open: bool


class CapabilitiesResponse(BaseModel):
    fulltext_search: str = "unavailable"
    llm_configured: bool
    storage_backends: list[str] = []
    registration_open: bool
    capture_available: bool = True
