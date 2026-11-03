# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from app.content import CapturedBlock
from app.schemas.annotation import AnnotationCreate
from app.schemas.reading import ReadingStylePatch, patch_preferences, resolve_preferences
from app.services.annotations import annotation_texts, selected_text


def test_preorder_inlines_legacy_and_utf16_ranges() -> None:
    blocks = [
        CapturedBlock.model_validate(
            {
                "type": "list",
                "children": [
                    {
                        "type": "list_item",
                        "text": "unused",
                        "inlines": [{"text": "中文"}, {"text": "😀链接", "bold": True}],
                    },
                    {"type": "image", "alt": "not selectable"},
                    {"type": "code", "text": "code", "inlines": [{"text": "unused"}]},
                ],
            }
        )
    ]
    texts = annotation_texts("fallback", blocks)
    assert texts == ["", "中文😀链接", "", "code"]
    assert annotation_texts("旧笔记\n\n第二段", []) == ["旧笔记\n\n第二段"]
    base = {"block_index": 1, "start_offset": 2, "end_offset": 5, "highlight_color": "yellow"}
    assert selected_text(texts, AnnotationCreate(**base)) == "😀链"
    for override in (
        {"start_offset": 3},
        {"end_offset": 3},
        {"end_offset": 7},
        {"block_index": 0},
        {"block_index": 9},
        {"selected_text": "错误选区"},
    ):
        with pytest.raises(ValueError):
            selected_text(texts, AnnotationCreate(**{**base, **override}))


def test_partial_reading_styles_reset_and_validate_css() -> None:
    values = patch_preferences(
        {"theme": "focus", "font_size": 24}, ReadingStylePatch(theme="compact", line_height=1.7)
    )
    assert values == {"theme": "compact", "line_height": 1.7}
    assert resolve_preferences(values).font_size == 16
    values = patch_preferences(values, ReadingStylePatch(line_height=None))
    assert resolve_preferences(values).line_height == 1.4
    assert patch_preferences(values, ReadingStylePatch()) == values
    assert resolve_preferences({}).background_color == "#fefce8"
    for value in (
        {"font_size": True},
        {"font_size": 25},
        {"line_height": float("nan")},
        {"background_color": "url(https://example.com)"},
        {"font_family": "evil"},
    ):
        with pytest.raises(ValueError):
            ReadingStylePatch.model_validate(value)


def test_online_font_and_dynamic_color_contracts() -> None:
    font = {
        "id": "noto-sans-sc",
        "family": "Noto Sans SC",
        "version": "5.3.1",
        "variable": True,
        "weights": [400, 500, 600, 700],
    }
    current = patch_preferences(
        {},
        ReadingStylePatch(
            font_family="online", online_font=font, color_mode="monet", monet_seed="#2488cc"
        ),
    )
    style = resolve_preferences(current)
    assert style.online_font.id == "noto-sans-sc"
    assert style.monet_scheme == "system"
    assert style.color_mode == "monet"
    assert (
        resolve_preferences(
            patch_preferences(current, ReadingStylePatch(theme="compact"))
        ).online_font
        is None
    )
    assert "online_font" not in patch_preferences(current, ReadingStylePatch(online_font=None))
    for invalid in (
        {"id": "../evil"},
        {"id": "https://example.com/font"},
        {"family": 'Bad";src:url(evil)'},
        {"version": "latest"},
        {"weights": []},
        {"weights": [450]},
        {"url": "https://example.com"},
    ):
        with pytest.raises(ValueError):
            ReadingStylePatch(online_font={**font, **invalid})
    for invalid in ({"color_mode": "auto"}, {"monet_seed": "red"}, {"monet_scheme": "custom"}):
        with pytest.raises(ValueError):
            ReadingStylePatch.model_validate(invalid)
