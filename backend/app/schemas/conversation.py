# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.summary import SummaryJobResponse

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Question
    request_key: str = Field(min_length=1, max_length=128)


class ConversationMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    turn_index: int = Field(ge=0, strict=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=24000)
    created_at: AwareDatetime


class ConversationJobResponse(SummaryJobResponse):
    turn_index: int


class ConversationHistory(BaseModel):
    turns: list[ConversationMessage]
    next_before: int | None
    latest_job: ConversationJobResponse | None
