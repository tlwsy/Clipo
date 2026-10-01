# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Theme = Literal["comfortable", "compact", "focus", "print"]
FontFamily = Literal["system-ui", "serif", "sans-serif"]
FontSize = Annotated[int, Field(strict=True, ge=14, le=24)]
FontWeight = Literal[400, 500, 600, 700]
LineHeight = Annotated[float, Field(ge=1.2, le=2.0, allow_inf_nan=False)]
ParagraphSpacing = Annotated[int, Field(strict=True, ge=0, le=40)]
ContentWidth = Annotated[int, Field(strict=True, ge=600, le=900)]
TextAlign = Literal["left", "justify"]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class ReadingPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Theme
    font_family: FontFamily
    font_size: FontSize
    font_weight: FontWeight
    line_height: LineHeight
    paragraph_spacing: ParagraphSpacing
    content_width: ContentWidth
    text_align: TextAlign
    background_color: Color
    text_color: Color


class ReadingStylePatch(BaseModel):
    """Omitted fields stay unchanged; null removes an override; theme resets the scope."""

    model_config = ConfigDict(extra="forbid")
    theme: Theme | None = None
    font_family: FontFamily | None = None
    font_size: FontSize | None = None
    font_weight: FontWeight | None = None
    line_height: LineHeight | None = None
    paragraph_spacing: ParagraphSpacing | None = None
    content_width: ContentWidth | None = None
    text_align: TextAlign | None = None
    background_color: Color | None = None
    text_color: Color | None = None


THEMES: dict[str, ReadingPreferences] = {
    name: ReadingPreferences(
        theme=name,
        font_family="system-ui",
        font_weight=400,
        font_size=size,
        line_height=line,
        paragraph_spacing=spacing,
        content_width=width,
        text_align=align,
        background_color=background,
        text_color=color,
    )
    for name, size, line, spacing, width, align, background, color in (
        ("comfortable", 18, 1.6, 16, 720, "left", "#fefce8", "#1c1917"),
        ("compact", 16, 1.4, 12, 680, "left", "#ffffff", "#0a0a0a"),
        ("focus", 20, 1.8, 20, 600, "left", "#1c1917", "#fafafa"),
        ("print", 16, 1.5, 12, 900, "justify", "#ffffff", "#000000"),
    )
}


def resolve_preferences(values: dict) -> ReadingPreferences:
    clean = ReadingStylePatch.model_validate(values).model_dump(exclude_none=True)
    return ReadingPreferences.model_validate(
        {**THEMES[clean.get("theme", "comfortable")].model_dump(), **clean}
    )


def patch_preferences(current: dict, patch: ReadingStylePatch) -> dict:
    values = patch.model_dump(exclude_unset=True)
    result = {} if "theme" in values else dict(current)
    for key, value in values.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result
