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
