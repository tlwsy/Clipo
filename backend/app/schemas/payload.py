"""Bounded, untrusted browser DOM input; never accepts cookies or executable HTML."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security.urls import UnsafeURL, normalize_url


def safe_url(value: str) -> str:
    try:
        return normalize_url(value)
    except UnsafeURL as exc:
        raise ValueError("链接必须为公开 HTTP(S) 地址") from exc


DIRECT_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
CHUNK_BYTES = 256 * 1024


class PayloadComment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=1, max_length=20000)
    likes: int = Field(default=0, ge=0, le=2**31 - 1, strict=True)
    replies: int = Field(default=0, ge=0, le=2**31 - 1, strict=True)


class CapturePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=2000)
    text: str = Field(min_length=1, max_length=8_000_000)
    author: str | None = Field(default=None, max_length=500)
    author_url: str | None = Field(default=None, max_length=4096)
    published_at: datetime | None = None
    images: list[Annotated[str, Field(max_length=4096)]] = Field(
        default_factory=list, max_length=1000
    )
    comments: list[PayloadComment] = Field(default_factory=list, max_length=100)
    selection: str | None = Field(default=None, max_length=50000)
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(
        default_factory=list, max_length=20
    )
    capture_warnings: list[Annotated[str, Field(max_length=500)]] = Field(
        default_factory=list, max_length=10
    )

    @field_validator("title", "text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("正文与标题不能为空或包含空字符")
        return value

    @field_validator("author_url")
    @classmethod
    def safe_author(cls, value: str | None) -> str | None:
        return safe_url(value) if value else None

    @field_validator("images")
    @classmethod
    def safe_images(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(safe_url(value) for value in values))
