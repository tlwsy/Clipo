# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.extractors.base import CapturedContent
from app.schemas.payload import MAX_UPLOAD_BYTES, CapturePayload
from app.security.urls import UnsafeURL, normalize_url

JobStatus = Literal["uploading", "queued", "running", "retrying", "failed", "success"]


class CaptureURL(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=4096)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        try:
            return normalize_url(value)
        except UnsafeURL as exc:
            raise ValueError(str(exc)) from exc


class CaptureRequest(CaptureURL):
    payload: CapturePayload | None = None


class UploadRequest(CaptureURL):
    total_bytes: int = Field(ge=1, le=MAX_UPLOAD_BYTES, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: str = Field(validation_alias="id")
    url: str
    status: JobStatus
    attempts: int
    last_error: str | None
    note_id: int | None
    cached: bool
    next_retry_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobPage(BaseModel):
    items: list[JobResponse]
    next_cursor: str | None


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    platform: str
    origin_url: str
    author: str | None
    author_url: str | None
    published_at: datetime | None


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    author: str | None
    content: str
    likes: int
    replies: int
    position: int
    ai_score: float | None
    ai_reason: str | None
    is_valuable: bool


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class TagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("标签不能为空")
        return value


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_favorite: bool = Field(strict=True)


class NoteItem(BaseModel):
    id: int
    title: str
    url: str
    platform: str
    author: str | None
    summary_excerpt: str
    status: Literal["ready", "original_only"]
    created_at: datetime
    is_favorite: bool
    tags: list[TagResponse]


class NotePage(BaseModel):
    items: list[NoteItem]
    next_cursor: str | None


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    url: str
    source: SourceResponse
    content: CapturedContent
    comments: list[CommentResponse]
    summary_markdown: str | None
    key_points: list[str]
    suggested_tags: list[str]
    tags: list[TagResponse]
    is_favorite: bool
    status: Literal["ready", "original_only"]
    summary_error: str | None
    comment_score_error: str | None
    created_at: datetime
    updated_at: datetime
