# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class MemoryNote(BaseModel):
    id: int
    title: str
    url: str
    summary_snippet: str
    key_points: list[str]
    platform: str
    site_name: str | None
    created_at: datetime
    annotations_count: int
    has_summary: bool
    is_favorite: bool


class MemoryGallery(BaseModel):
    notes: list[MemoryNote]


class NoteView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_seconds: int = Field(strict=True, ge=0, le=300)


class MemoryDismiss(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note_id: int = Field(strict=True, gt=0)


class MemoryHistory(BaseModel):
    last_viewed_at: AwareDatetime | None = None
    reading_duration_seconds: int = Field(default=0, strict=True, ge=0, le=2147483647)
    memory_dismissed_at: AwareDatetime | None = None
