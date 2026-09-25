# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Versioned, inert article content shared by capture, reading and export."""

import re
from collections.abc import Iterator
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def checked_url(value: str | None) -> str | None:
    if value is None:
        return None
    # Local import avoids the URL error -> extractor contract dependency cycle.
    from app.security.urls import UnsafeURL, normalize_url

    try:
        return normalize_url(value)
    except UnsafeURL as exc:
        raise ValueError("内容链接须为公开 HTTP(S) 地址") from exc


class ContentInline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=1_000_000)
    url: str | None = Field(default=None, max_length=4096)
    bold: bool = False
    italic: bool = False
    strike: bool = False
    code: bool = False

    _url = field_validator("url")(checked_url)


class CapturedBlock(BaseModel):
    """No HTML, CSS, scripts or arbitrary attributes are accepted."""

    model_config = ConfigDict(extra="forbid")
    type: Literal[
        "text",
        "heading",
        "image",
        "game_card",
        "quote",
        "code",
        "list",
        "list_item",
        "table",
        "table_row",
        "table_cell",
        "details",
        "divider",
    ]
    text: str = Field(default="", max_length=1_000_000)
    inlines: list[ContentInline] = Field(default_factory=list, max_length=10000)
    children: list["CapturedBlock"] = Field(default_factory=list, max_length=10000)
    url: str | None = Field(default=None, max_length=4096)
    image: str | None = Field(default=None, max_length=4096)
    alt: str = Field(default="", max_length=10000)
    level: int = Field(default=2, ge=1, le=6)
    ordered: bool = False
    header: bool = False
    width: int | None = Field(default=None, ge=1, le=100000)
    height: int | None = Field(default=None, ge=1, le=100000)
    appid: str | None = Field(default=None, pattern=r"^[0-9]{1,12}$")
    store: Literal["steam", "epic"] | None = None

    _urls = field_validator("url", "image")(checked_url)


def bounded_blocks(value: Any) -> Any:
    """Bound before recursive model validation, including untrusted imports."""
    if not isinstance(value, list):
        raise ValueError("正文内容块须为列表")
    pending = [(value, 0)]
    nodes = 0
    characters = 0
    while pending:
        rows, depth = pending.pop()
        if depth > 16:
            raise ValueError("正文嵌套层级过多")
        for item in rows:
            row = item.model_dump() if isinstance(item, CapturedBlock) else item
            if not isinstance(row, dict):
                raise ValueError("正文内容块格式无效")
            nodes += 1
            for key in ("text", "alt"):
                if isinstance(row.get(key), str):
                    characters += len(row[key])
            spans = row.get("inlines", [])
            if isinstance(spans, list):
                nodes += len(spans)
                characters += sum(
                    len(s.get("text", ""))
                    for s in spans
                    if isinstance(s, dict) and isinstance(s.get("text", ""), str)
                )
            if nodes > 20000 or characters > 8_000_000:
                raise ValueError("正文结构超过大小限制")
            children = row.get("children", [])
            if isinstance(children, list) and children:
                pending.append((children, depth + 1))
    return value


def walk_blocks(blocks: list[CapturedBlock]) -> Iterator[CapturedBlock]:
    for block in blocks:
        yield block
        yield from walk_blocks(block.children)


def blocks_text(blocks: list[CapturedBlock]) -> str:
    return "\n\n".join(
        value
        for block in walk_blocks(blocks)
        if (
            value := ("".join(span.text for span in block.inlines) if block.inlines else block.text)
            or block.alt
        )
    )


def blocks_images(blocks: list[CapturedBlock]) -> list[str]:
    return list(
        dict.fromkeys(
            block.url for block in walk_blocks(blocks) if block.type == "image" and block.url
        )
    )


def blocks_markdown(blocks: list[CapturedBlock]) -> str:
    def escape(value: str) -> str:
        return re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", value)

    def render(block: CapturedBlock) -> str:
        body = escape(block.text)
        if block.inlines:
            spans = []
            for span in block.inlines:
                value = escape(span.text)
                if span.bold:
                    value = f"**{value}**"
                if span.italic:
                    value = f"*{value}*"
                if span.url:
                    value = f"[{value}](<{span.url}>)"
                spans.append(value)
            body = "".join(spans)
        children = blocks_markdown(block.children)
        if block.type == "heading":
            return "#" * block.level + " " + body
        if block.type == "image":
            return f"![{escape(block.alt)}](<{block.url}>)" if block.url else escape(block.alt)
        if block.type == "game_card":
            label = body or "游戏卡片"
            return f"[{label}](<{block.url}>)" if block.url else label
        if block.type == "quote":
            return "\n".join("> " + line for line in (body + children).splitlines())
        if block.type == "code":
            return "\n".join("    " + line for line in block.text.splitlines())
        if block.type == "list":
            return "\n".join(
                (f"{i + 1}. " if block.ordered else "- ") + render(child).replace("\n", "\n   ")
                for i, child in enumerate(block.children)
            )
        if block.type == "table":
            rows = [
                [render(cell).replace("\n", " ").replace("|", "\\|") for cell in row.children]
                for row in block.children
            ]
            if not rows:
                return ""
            width = max(map(len, rows))
            lines = ["| " + " | ".join(row + [""] * (width - len(row))) + " |" for row in rows]
            lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
            return "\n".join(lines)
        if block.type == "details":
            return f"**{body or '展开内容'}**\n\n{children}"
        if block.type == "divider":
            return "---"
        return "\n\n".join(part for part in (body, children) if part)

    return "\n\n".join(render(block) for block in blocks)
