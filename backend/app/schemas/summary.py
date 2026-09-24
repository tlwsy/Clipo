# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=128)


class SummaryJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    note_id: int
    status: Literal["queued", "running", "retrying", "failed", "success"]
    attempts: int
    last_error: str | None
    next_retry_at: datetime | None
    created_at: datetime
    updated_at: datetime
