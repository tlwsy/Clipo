# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stable preorder block indices and UTF-16 offsets matching DOM Range/JavaScript."""

from app.content import CapturedBlock, walk_blocks
from app.schemas.annotation import AnnotationCreate

TEXT_BLOCKS = {"text", "heading", "quote", "code", "list_item", "table_cell", "details"}


def annotation_texts(text: str, blocks: list[CapturedBlock]) -> list[str]:
    if not blocks:
        return [text]
    return [
        (
            (
                block.text
                if block.type == "code" or not block.inlines
                else "".join(span.text for span in block.inlines)
            )
            if block.type in TEXT_BLOCKS
            else ""
        )
        for block in walk_blocks(blocks)
    ]


def selected_text(texts: list[str], annotation: AnnotationCreate) -> str:
    if annotation.block_index >= len(texts):
        raise ValueError("标注所在内容块不存在")
    text = texts[annotation.block_index].encode("utf-16-le")
    start, end = annotation.start_offset * 2, annotation.end_offset * 2
    if start < 0 or end <= start or end > len(text):
        raise ValueError("标注范围超出正文")
    try:
        # Strict decoding rejects half of an emoji/surrogate pair at either endpoint.
        quote = text[start:end].decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise ValueError("标注范围必须包含完整字符") from exc
    if not quote.strip():
        raise ValueError("请选择非空白正文")
    if annotation.selected_text is not None and annotation.selected_text != quote:
        raise ValueError("正文已变化，请刷新后重新选择")
    return quote
