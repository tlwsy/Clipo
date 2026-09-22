# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, model_validator

from app.schemas.capture import NoteResponse, TagRequest
from app.security.urls import normalize_url

MAX_IMPORT_BYTES = 100 * 1024 * 1024


class ArchiveNote(NoteResponse):
    model_config = ConfigDict(extra="forbid")
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Archive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["clipo-library"] = "clipo-library"
    version: Literal[1] = 1
    exported_at: AwareDatetime
    tags: list[TagRequest]
    notes: list[ArchiveNote]

    @model_validator(mode="after")
    def validate_references(self) -> "Archive":
        ids = [note.id for note in self.notes]
        names = [tag.name for tag in self.tags]
        if len(set(ids)) != len(ids) or len(set(names)) != len(names):
            raise ValueError("重复的笔记或标签")
        for note in self.notes:
            if len(note.source.platform) > 40:
                raise ValueError("平台名称过长")
            for url in (
                note.url,
                note.source.origin_url,
                note.content.url,
                note.source.author_url,
                note.content.author_url,
                *note.content.images,
            ):
                if url:
                    try:
                        normalize_url(url)
                    except Exception as exc:
                        raise ValueError("媒体与来源须为公开网页链接") from exc
            if note.source.published_at and note.source.published_at.tzinfo is None:
                raise ValueError("时间必须包含时区")
            if any(tag.name not in names for tag in note.tags):
                raise ValueError("缺少引用的标签")
            positions = [comment.position for comment in note.comments]
            if len(set(positions)) != len(positions):
                raise ValueError("重复的评论位置")
        return self


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=100)


class BackupJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: Literal["export", "import", "backup"]
    status: Literal["queued", "running", "retrying", "success", "failed"]
    attempts: int
    note_count: int | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class BackupSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["none", "local", "s3", "webdav"] = "none"
    schedule: str = Field(default="", max_length=100)
    endpoint: str = Field(default="", max_length=2048)
    bucket: str = Field(default="", max_length=63, pattern=r"^[a-z0-9.-]*$")
    region: str = Field(
        default="us-east-1", min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9-]+$"
    )
    prefix: str = Field(default="clipo", max_length=200, pattern=r"^[a-zA-Z0-9_/-]*$")
    username: str = Field(default="", max_length=200)
    access_key: SecretStr | None = Field(default=None, max_length=4096)
    secret: SecretStr | None = Field(default=None, max_length=4096)
    clear_credentials: bool = False


class BackupSettingsResponse(BaseModel):
    target: Literal["none", "local", "s3", "webdav"]
    schedule: str
    endpoint: str
    bucket: str
    region: str
    prefix: str
    username: str
    access_key_set: bool
    secret_set: bool
    timezone: str
    local_keep: int
    download_retention_days: int
