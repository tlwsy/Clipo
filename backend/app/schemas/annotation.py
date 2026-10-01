# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

HighlightColor = Literal["yellow", "green", "blue", "pink"]
AnnotationText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=5000, pattern=r"^[^\x00]*$")
]
Offset = Annotated[int, Field(strict=True, ge=0, le=8_000_000)]


class AnnotationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    highlight_color: HighlightColor | None = None
    note_text: AnnotationText | None = None


class AnnotationCreate(AnnotationUpdate):
    block_index: int = Field(strict=True, ge=0, lt=20000)
    start_offset: Offset
    end_offset: Offset
    selected_text: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def valid_annotation(self) -> "AnnotationCreate":
        if not 0 < self.end_offset - self.start_offset <= 10000:
            raise ValueError("请选择 1–10000 个字符的正文")
        if not self.highlight_color and not self.note_text:
            raise ValueError("请选择高亮颜色或填写批注")
        return self


class AnnotationResponse(AnnotationCreate):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: int
    selected_text: str = Field(max_length=10000)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class AnnotationPage(BaseModel):
    annotations: list[AnnotationResponse]
