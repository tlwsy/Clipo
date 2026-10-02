# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inert, self-contained single-note exports. Never fetch media or run a model."""

import re
import unicodedata
from collections import defaultdict
from datetime import UTC
from html import escape
from typing import Any
from urllib.parse import quote

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markupsafe import Markup

from app.content import CapturedBlock, ContentInline, walk_blocks
from app.note_repository import NoteRepository
from app.schemas.annotation import AnnotationResponse
from app.schemas.note_export import ExportOptions
from app.security.urls import UnsafeURL, normalize_url
from app.services.annotations import TEXT_BLOCKS, annotation_texts
from app.services.notes import read_note

COLORS = {"yellow": "黄色", "green": "绿色", "blue": "蓝色", "pink": "粉色"}
EXPORT_CSP = (
    "default-src 'none'; img-src https: http:; style-src 'unsafe-inline'; "
    "base-uri 'none'; form-action 'none'"
)


def safe_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return normalize_url(value)
    except UnsafeURL:
        return None


def markdown_text(value: str) -> str:
    # Source text is data, including apparent headings, links and raw HTML.
    return re.sub(r"([\\`*_{}\[\]<>#!|~+.\-])", r"\\\1", value.replace("\r", ""))


def markdown_link(label: str, url: str | None, image: bool = False) -> str:
    if not (url := safe_url(url)):
        return markdown_text(label)
    encoded = quote(url, safe="/:?#[]@!$&'()*+,;=%~_-")
    return f"{'!' if image else ''}[{markdown_text(label)}](<{encoded}>)"


def html_link(label: str, url: str | None) -> str:
    if not (url := safe_url(url)):
        return escape(label)
    return f'<a href="{escape(url, quote=True)}" rel="noreferrer noopener">{escape(label)}</a>'


def summary_html(value: str) -> Markup:
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    parser.validateLink = lambda url: safe_url(url) is not None

    def image_as_link(tokens: list[Token], index: int, options: Any, env: Any) -> str:
        token = tokens[index]
        return html_link(token.content or "查看引用图片", token.attrGet("src"))

    parser.renderer.rules["image"] = image_as_link
    return Markup(parser.render(value))


def export_filename(title: str, note_id: int, extension: str) -> str:
    title = "".join(
        char
        for char in title
        if not unicodedata.category(char).startswith("C") and char not in '/\\:*?"<>|'
    )
    title = " ".join(title.split())[:80].strip(" .") or "笔记"
    return f"{title}-{note_id}.{extension}"


def _annotation_ranges(
    text: str, annotations: list[AnnotationResponse]
) -> list[tuple[int, int, AnnotationResponse]]:
    """Convert only requested UTF-16 endpoints; reject stale and split-surrogate anchors."""
    if not annotations:
        return []
    wanted = {offset for a in annotations for offset in (a.start_offset, a.end_offset)}
    positions = {0: 0}
    offset = 0
    for index, char in enumerate(text):
        offset += 2 if ord(char) > 0xFFFF else 1
        if offset in wanted:
            positions[offset] = index + 1
    ranges = []
    for item in annotations:
        start, end = positions.get(item.start_offset), positions.get(item.end_offset)
        if start is not None and end is not None and text[start:end] == item.selected_text:
            ranges.append((start, end, item))
    return ranges


def annotated_html(block: CapturedBlock, annotations: list[AnnotationResponse]) -> str:
    spans = (
        block.inlines
        if block.inlines and block.type != "code"
        else [ContentInline(text=block.text)]
    )
    spans = [span for span in spans if span.text]
    text = "".join(span.text for span in spans)
    ranges = _annotation_ranges(text, annotations)
    starts: dict[int, list[AnnotationResponse]] = defaultdict(list)
    ends: dict[int, list[AnnotationResponse]] = defaultdict(list)
    cuts = {0, len(text)}
    for start, end, item in ranges:
        starts[start].append(item)
        ends[end].append(item)
        cuts.update((start, end))
    boundaries = []
    offset = 0
    for span in spans:
        offset += len(span.text)
        boundaries.append(offset)
        cuts.add(offset)
    points = sorted(cuts)
    active: dict[int, AnnotationResponse] = {}
    output = []
    span_index = 0
    for start, end in zip(points, points[1:], strict=False):
        for item in ends[start]:
            active.pop(item.id, None)
        for item in starts[start]:
            active[item.id] = item
        while boundaries[span_index] <= start:
            span_index += 1
        span = spans[span_index]
        value = escape(text[start:end])
        if active:
            items = sorted(active.values(), key=lambda item: item.id)
            color = next(
                (item.highlight_color for item in reversed(items) if item.highlight_color), "none"
            )
            # A short hover preview avoids multiplying 1000 long notes across many spans.
            notes = [item.note_text for item in items if item.note_text]
            tooltip = (
                "\n".join(value[:160] for value in notes[-3:]) + "\n完整批注见文末标注列表"
                if notes
                else "高亮标注"
            )
            value = (
                f'<mark class="highlight-{color}" title="{escape(tooltip, quote=True)}">'
                f"{value}</mark>"
            )
        for enabled, tag in (
            (span.code, "code"),
            (span.bold, "strong"),
            (span.italic, "em"),
            (span.strike, "del"),
        ):
            if enabled:
                value = f"<{tag}>{value}</{tag}>"
        if url := safe_url(span.url):
            value = f'<a href="{escape(url, quote=True)}" rel="noreferrer noopener">{value}</a>'
        output.append(value)
    return "".join(output)


def _html_image(url: str | None, alt: str) -> str:
    if not (url := safe_url(url)):
        return escape(alt)
    return (
        f'<figure><img src="{escape(url, quote=True)}" alt="{escape(alt, quote=True)}" '
        f'referrerpolicy="no-referrer"><figcaption>{escape(alt)}</figcaption></figure>'
    )


class ExportService:
    def __init__(self, repository: NoteRepository, note_id: int, options: ExportOptions) -> None:
        self.note = read_note(repository, note_id)
        self.options = options
        self.annotations = self.note.annotations if options.include_annotations else []
        self.grouped: dict[int, list[AnnotationResponse]] = defaultdict(list)
        for item in self.annotations:
            self.grouped[item.block_index].append(item)
        self.indices = {
            id(block): i for i, block in enumerate(walk_blocks(self.note.content.blocks))
        }

    def _html_block(self, block: CapturedBlock) -> str:
        annotations = self.grouped[self.indices[id(block)]] if block.type in TEXT_BLOCKS else []
        body = annotated_html(block, annotations)
        rendered_children = [self._html_block(child) for child in block.children]
        children = "".join(rendered_children)
        if block.type == "image":
            return _html_image(block.url, block.alt)
        if block.type == "game_card":
            return (
                '<aside class="game-card">'
                + _html_image(block.image, "游戏封面")
                + html_link(block.text or "游戏卡片", block.url)
                + "</aside>"
            )
        if block.type == "divider":
            return "<hr>"
        if block.type == "code":
            return f"<pre><code>{body}</code></pre>"
        if block.type == "details":
            return (
                '<section class="expanded-details">'
                f'<h3>{body or "展开内容"}</h3>{children}</section>'
            )
        if block.type == "table":
            if (
                block.children
                and block.children[0].children
                and all(cell.header for cell in block.children[0].children)
            ):
                header = rendered_children[0]
                rows = "".join(rendered_children[1:])
                return f"<table><thead>{header}</thead><tbody>{rows}</tbody></table>"
            return f"<table><tbody>{children}</tbody></table>"
        tag = {
            "text": "div",
            "heading": f"h{max(2, block.level)}",
            "quote": "blockquote",
            "list": "ol" if block.ordered else "ul",
            "list_item": "li",
            "table_row": "tr",
            "table_cell": "th" if block.header else "td",
        }[block.type]
        attribute = ' class="paragraph"' if block.type == "text" else ""
        return f"<{tag}{attribute}>{body}{children}</{tag}>"

    def _markdown_block(self, block: CapturedBlock) -> str:
        body = markdown_text(block.text)
        if block.inlines and block.type != "code":
            parts = []
            for span in block.inlines:
                value = markdown_text(span.text)
                if span.code:
                    # HTML code is unnecessary; backtick fences adapt to literal backticks.
                    fence = "`" * (
                        max((len(s) for s in re.findall(r"`+", span.text)), default=0) + 1
                    )
                    value = f"{fence} {span.text} {fence}"
                if span.bold:
                    value = f"**{value}**"
                if span.italic:
                    value = f"*{value}*"
                if span.strike:
                    value = f"~~{value}~~"
                if url := safe_url(span.url):
                    value = f"[{value}](<{quote(url, safe='/:?#[]@!$&()*+,;=%~_-')}>)"
                parts.append(value)
            body = "".join(parts)
        rendered_children = (
            [self._markdown_block(child) for child in block.children]
            if block.type != "table"
            else []
        )
        children = "\n\n".join(rendered_children)
        if block.type == "heading":
            return "#" * max(3, block.level) + " " + body
        if block.type == "image":
            return markdown_link(block.alt, block.url, image=True)
        if block.type == "game_card":
            return "\n\n".join(
                [
                    markdown_link(block.text or "游戏卡片", block.url),
                    markdown_link("游戏封面", block.image, True),
                ]
                if block.image
                else [markdown_link(block.text or "游戏卡片", block.url)]
            )
        if block.type == "quote":
            return "\n".join(
                "> " + line for line in (body + "\n\n" + children).strip().splitlines()
            )
        if block.type == "code":
            fence = "`" * max(
                3, max((len(s) for s in re.findall(r"`+", block.text)), default=0) + 1
            )
            return f"{fence}\n{block.text}\n{fence}"
        if block.type == "list":
            lines = []
            for i, child in enumerate(rendered_children):
                prefix = f"{i + 1}. " if block.ordered else "- "
                lines.append(prefix + child.replace("\n", "\n" + " " * len(prefix)))
            return "\n".join(lines)
        if block.type == "table":
            rows = [
                [self._markdown_block(cell).replace("\n", "<br>") for cell in row.children]
                for row in block.children
            ]
            if not rows or not any(rows):
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

    def _context(self) -> dict[str, Any]:
        note = self.note
        platform = {
            "xiaohongshu": "小红书",
            "xiaoheihe": "小黑盒",
            "bilibili": "哔哩哔哩",
            "youtube": "YouTube",
        }.get(note.source.platform, note.source.site_name or "网页")
        metadata = [("来源", platform)]
        if note.source.author:
            metadata.append(("作者", note.source.author))
        if note.source.published_at:
            metadata.append(
                (
                    "发布时间",
                    note.source.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC"),
                )
            )
        metadata.append(
            ("保存时间", note.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC"))
        )
        if note.tags:
            metadata.append(("标签", "、".join(tag.name for tag in note.tags)))
        included = {
            url
            for block in walk_blocks(note.content.blocks)
            for url in (block.url if block.type == "image" else None, block.image)
            if url
        }
        texts = annotation_texts(note.content.text, note.content.blocks)
        valid_ids = {
            item.id
            for index, text in enumerate(texts)
            for _, _, item in _annotation_ranges(text, self.grouped[index])
        }
        return {
            "note": note,
            "options": self.options,
            "metadata": metadata,
            "annotations": self.annotations,
            "valid_ids": valid_ids,
            "comments": (
                [row for row in note.comments if row.is_valuable]
                if self.options.include_comments
                else []
            ),
            "extra_images": [
                url for url in note.content.images if url not in included and safe_url(url)
            ],
            "colors": COLORS,
            "csp": EXPORT_CSP,
        }

    def export_markdown(self) -> str:
        content = self.note.content
        body = (
            "\n\n".join(self._markdown_block(block) for block in content.blocks)
            if content.blocks
            else markdown_text(content.text or "这篇内容没有文字正文。")
        )
        return (
            _templates.get_template("note.md.jinja").render(**self._context(), body=body).strip()
            + "\n"
        )

    def export_html(self) -> str:
        content = self.note.content
        body = (
            "".join(self._html_block(block) for block in content.blocks)
            if content.blocks
            else '<div class="paragraph">'
            + annotated_html(
                CapturedBlock(type="text", text=content.text or "这篇内容没有文字正文。"),
                self.grouped[0],
            )
            + "</div>"
        )
        return _templates.get_template("note.html.jinja").render(
            **self._context(), body=Markup(body)
        )


_templates = Environment(
    loader=PackageLoader("app", "templates/exports"),
    autoescape=select_autoescape(enabled_extensions=("html.jinja",)),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)
_templates.filters.update(
    md=markdown_text,
    md_link=markdown_link,
    # Keep the model's Markdown structure while rendering raw HTML as literal text.
    md_summary=lambda value: escape(value, quote=False),
    summary_html=summary_html,
    safe_url=safe_url,
)
