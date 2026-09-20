from typing import Annotated

from pydantic import BaseModel, Field, HttpUrl, SecretStr, StringConstraints


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


class SettingsUpdate(BaseModel):
    llm: LlmUpdate | None = None


class LlmResponse(BaseModel):
    base_url: str
    model: str
    api_key_set: bool
    comment_score_threshold: float
    max_comments: int
    text_token_budget: int
    overridden_fields: list[str]


class SettingsResponse(BaseModel):
    llm: LlmResponse


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
