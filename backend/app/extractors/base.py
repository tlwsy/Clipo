from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field


class CapturedComment(BaseModel):
    author: str | None = None
    content: str
    likes: int = 0
    replies: int = 0


class CapturedContent(BaseModel):
    url: str
    platform: str = "web"
    title: str
    text: str
    author: str | None = None
    author_url: str | None = None
    published_at: datetime | None = None
    images: list[str] = Field(default_factory=list)
    comments: list[CapturedComment] = Field(default_factory=list)
    raw_html: str | None = None


class ExtractionError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class Extractor(Protocol):
    name: str

    def matches(self, url: str) -> bool: ...

    def extract(self, url: str, payload: dict | None = None) -> CapturedContent: ...
