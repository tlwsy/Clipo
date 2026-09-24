# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ShareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_in_days: Literal[1, 7, 30] | None = 7


class ShareResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class IssuedShareResponse(ShareResponse):
    token: str


class PublicReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: SecretStr = Field(min_length=43, max_length=43)


class PublicComment(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    author: str | None
    content: str
    likes: int
    replies: int
    ai_score: float | None
    ai_reason: str | None
    is_valuable: bool


class PublicNoteResponse(BaseModel):
    title: str
    url: str | None
    platform: str
    author: str | None
    published_at: datetime | None
    text: str
    images: list[str]
    summary_markdown: str | None
    key_points: list[str]
    comments: list[PublicComment]
