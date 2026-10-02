# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from app.content import CapturedBlock
from app.schemas.annotation import AnnotationResponse
from app.services.note_export import annotated_html, export_filename, summary_html
from lxml import html


def annotation(**changes: object) -> AnnotationResponse:
    return AnnotationResponse.model_validate(
        {
            "id": 1,
            "block_index": 0,
            "start_offset": 1,
            "end_offset": 4,
            "selected_text": "😀链",
            "highlight_color": "yellow",
            "note_text": '<script>私人批注</script>"',
            "created_at": "2026-10-02T00:00:00Z",
            "updated_at": "2026-10-02T00:00:00Z",
            **changes,
        }
    )


def test_export_annotations_preserve_unicode_overlaps_and_inline_formatting() -> None:
    block = CapturedBlock.model_validate(
        {
            "type": "text",
            "inlines": [
                {"text": "中😀", "bold": True},
                {"text": "链接尾", "url": "https://example.com/", "italic": True},
                {"text": "", "bold": True},
            ],
        }
    )
    rendered = annotated_html(
        block,
        [
            annotation(),
            annotation(
                id=2, start_offset=3, end_offset=5, selected_text="链接", highlight_color="blue"
            ),
            annotation(id=3, selected_text="旧文字"),
            annotation(id=4, start_offset=2, end_offset=3, selected_text="😀"),
        ],
    )
    document = html.fragment_fromstring(rendered, create_parent="div")
    assert document.text_content() == "中😀链接尾"
    assert document.xpath(".//strong/mark")[0].text == "😀"
    assert document.xpath('.//mark[@class="highlight-blue"]')[0].text == "链"
    assert document.xpath(".//a")[0].get("href") == "https://example.com/"
    assert not document.xpath(".//script")
    assert not any("旧文字" in node.get("title", "") for node in document.xpath(".//mark"))
    assert "<script>" not in rendered


@pytest.mark.parametrize(
    "payload",
    [
        "<script>alert(1)</script><img src=x onerror=alert(1)>",
        "[链接](javascript:alert%281%29) ![图片](data:text/html,bad)",
        "[链接](file:///etc/passwd) [内网](http://127.0.0.1/private)",
        '<svg/onload=alert(1)> <iframe src="https://example.com"></iframe>',
        "[实体](jav&#x61;script:alert%281%29)",
    ],
)
def test_summary_renders_untrusted_markdown_as_inert_content(payload: str) -> None:
    document = html.fragment_fromstring(str(summary_html(payload)), create_parent="div")
    assert not document.xpath(".//script|.//iframe|.//svg|.//img")
    assert not document.xpath(".//*[@onerror or @onload]")
    assert not document.xpath(".//a")


def test_summary_keeps_markdown_format_and_uses_links_for_model_images() -> None:
    rendered = summary_html("## 摘要\n\n**重点**\n\n![引用](https://example.com/image.png)")
    document = html.fragment_fromstring(str(rendered), create_parent="div")
    assert document.xpath(".//h2")[0].text == "摘要"
    assert document.xpath(".//strong")[0].text == "重点"
    assert document.xpath(".//a")[0].get("href") == "https://example.com/image.png"
    assert not document.xpath(".//img")


def test_download_filename_has_no_path_header_or_bidi_injection() -> None:
    name = export_filename('../中文/\\:*?"<>|\r\n\u202efile', 42, "html")
    assert name == "中文file-42.html"
    assert export_filename("...", 42, "md") == "笔记-42.md"
    assert len(export_filename("中" * 200, 42, "md")) < 90


def test_empty_annotation_rendering_and_code_use_the_correct_source() -> None:
    assert annotated_html(CapturedBlock(type="text"), []) == ""
    block = CapturedBlock.model_validate(
        {"type": "code", "text": "中😀链接尾", "inlines": [{"text": "错误内容"}]}
    )
    document = html.fragment_fromstring(annotated_html(block, [annotation()]), create_parent="div")
    assert document.text_content() == "中😀链接尾"
    assert document.xpath(".//mark")[0].text == "😀链"
