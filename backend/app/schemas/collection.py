# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

CollectionColor = Literal["blue", "green", "purple", "orange", "pink", "red", "teal", "yellow"]
CollectionIcon = Literal["folder", "briefcase", "book", "heart", "laptop", "star"]
CollectionName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: CollectionName
    color: CollectionColor
    icon: CollectionIcon | None = None


class CollectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: CollectionName | None = None
    color: CollectionColor | None = None
    icon: CollectionIcon | None = None

    @model_validator(mode="after")
    def required_values(self) -> "CollectionUpdate":
        if any(getattr(self, key) is None for key in self.model_fields_set & {"name", "color"}):
            raise ValueError("名称和颜色不能为空")
        return self


class CollectionResponse(CollectionCreate):
    id: int
    note_count: int
    created_at: datetime
    updated_at: datetime


class CollectionPage(BaseModel):
    collections: list[CollectionResponse]


class CollectionNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=100)
