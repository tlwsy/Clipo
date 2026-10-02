# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelUsageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_limit: int | None = Field(ge=0, le=1000000, strict=True)


class ModelUsageResponse(BaseModel):
    month: str
    resets_at: datetime
    monthly_limit: int | None
    calls: int
    remaining: int | None
