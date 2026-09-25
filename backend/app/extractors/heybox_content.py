# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse Heybox's HTML and mixed blocks into inert, ordered article content."""

import json
import re
from typing import Any
from urllib.parse import unquote, urlsplit

from lxml import etree
from lxml import html as lxml_html

from app.content import CapturedBlock, ContentInline, blocks_images, blocks_text, walk_blocks
from app.extractors.structured import media_url, obj, text

SKIP_TAGS = {"script", "style", "noscript", "template", "iframe", "form", "input", "button", "svg"}
BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "img",
    "figure",
    "figcaption",
    "details",
    "table",
    "hr",
    "video",
}
MAX_BLOCKS = 5000
MAX_IMAGES = 1000


def readable_emojis(value: str) -> str:
    # Preserve the meaning of proprietary stickers without guessing artwork.
    return re.sub(r"\[cube_([^\]\r\n]{1,40})\]", r"[\1]", value)


def media_key(value: str) -> tuple[str, str]:
    parts = urlsplit(value)
    host = parts.hostname or ""
    if re.fullmatch(r"imgheybox\d*\.max-c\.com", host):
        return "imgheybox.max-c.com", parts.path
    return host, parts.path + ("?" + parts.query if parts.query else "")


def article_url(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if (
        parts.hostname == "api.xiaoheihe.cn"
        and parts.path.rstrip("/") == "/open_inapp"
        and parts.fragment.startswith("heybox://")
    ):
        value = parts.fragment
    if value.startswith("heybox://"):
        try:
            encoded = value.removeprefix("heybox://")
            for _ in range(2):
                encoded = unquote(encoded)
            target = obj(json.loads(encoded))
            kind = target.get("protocol_type")
            if kind == "openLink":
                identifier = str(obj(target.get("link")).get("linkid", ""))
                if re.fullmatch(r"[a-zA-Z0-9]{1,80}", identifier):
                    return f"https://www.xiaoheihe.cn/app/bbs/link/{identifier}"
            if kind == "openUser" and re.fullmatch(r"\d{1,20}", str(target.get("user_id", ""))):
                return f"https://www.xiaoheihe.cn/app/user/profile/{target['user_id']}"
        except (ValueError, TypeError):
            pass
        return None
    # Do not repair nonstandard author-entered domains by guessing.
    return media_url(value)


def dimension(value: Any) -> int | None:
    try:
        number = int(value)
        return number if 0 < number <= 100000 else None
    except (TypeError, ValueError, OverflowError):
        return None


def game_block(value: Any) -> CapturedBlock:
    identifier = str(value) if type(value) in (str, int) else ""
    return CapturedBlock(
        type="game_card",
        appid=identifier if re.fullmatch(r"\d{1,12}", identifier) else None,
        text="游戏卡片",
    )


def image_block(value: Any, caption: Any = "", **sizes: Any) -> CapturedBlock | None:
    url = media_url(value)
    if not url:
        return None
    caption = text(caption)
    # Mobile uploads sometimes put a private device cache path into `text`.
    if re.match(r"^(?:/|file:|[A-Za-z]:[\\/])", caption):
        caption = ""
    return CapturedBlock(
        type="image",
        url=url,
        alt=readable_emojis(caption[:10000]),
        width=dimension(sizes.get("width")),
        height=dimension(sizes.get("height")),
    )


class ArticleParser:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.nodes = 0

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def fragment(self, source: str) -> list[CapturedBlock]:
        try:
            root = lxml_html.fragment_fromstring(source, create_parent="div")
        except (etree.ParserError, ValueError):
            self.warn("部分正文标记无法解析，已保留可读取的文字。")
            return [CapturedBlock(type="text", text=readable_emojis(source))] if source else []
        return self.flow(root)

    def flow(self, root: Any, depth: int = 0) -> list[CapturedBlock]:
        result: list[CapturedBlock] = []
        spans: list[ContentInline] = []

        def add(value: str | None, marks: dict[str, Any]) -> None:
            if value:
                spans.append(ContentInline(text=readable_emojis(value), **marks))

        def flush() -> None:
            if spans and any(span.text.strip() for span in spans):
                result.append(CapturedBlock(type="text", inlines=list(spans)))
            spans.clear()

        def visit(node: Any, marks: dict[str, Any], level: int) -> None:
            self.nodes += 1
            if self.nodes > MAX_BLOCKS or level > 14:
                self.warn("正文结构超过解析上限，已保留取得的内容；请查看原网页补充。")
                return
            tag = str(getattr(node, "tag", "")).lower()
            if tag in SKIP_TAGS or not isinstance(node.tag, str) or node.get("hidden") is not None:
                return
            if tag == "br":
                add("\n", marks)
            elif tag in BLOCK_TAGS:
                flush()
                result.extend(self.element(node, level))
            else:
                updated = dict(marks)
                if tag in ("strong", "b"):
                    updated["bold"] = True
                if tag in ("em", "i"):
                    updated["italic"] = True
                if tag in ("s", "del", "strike"):
                    updated["strike"] = True
                if tag == "code":
                    updated["code"] = True
                if tag == "a":
                    url = article_url(node.get("href"))
                    if url:
                        updated["url"] = url
                    elif node.get("href"):
                        self.warn("部分链接格式无法安全识别，已保留链接文字。")
                add(node.text, updated)
                for child in node:
                    visit(child, updated, level + 1)
                    add(child.tail, updated)

        add(root.text, {})
        for child in root:
            visit(child, {}, depth + 1)
            add(child.tail, {})
        flush()
        return result

    def element(self, node: Any, depth: int) -> list[CapturedBlock]:
        tag = node.tag.lower()
        if tag == "img":
            if (
                node.get("data-type") == "game_card"
                or "mention-game" in node.get("class", "").split()
            ):
                return [game_block(node.get("data-gameid"))]
            image = image_block(
                node.get("data-original") or node.get("data-src") or node.get("src"),
                node.get("data-description") or node.get("alt"),
                width=node.get("data-width") or node.get("width"),
                height=node.get("data-height") or node.get("height"),
            )
            return [image] if image else []
        if tag == "hr":
            return [CapturedBlock(type="divider")]
        if tag == "pre":
            return [CapturedBlock(type="code", text="".join(node.itertext()))]
        if tag == "video":
            self.warn("视频以原始链接保留，未下载视频。")
            url = article_url(node.get("src"))
            return [CapturedBlock(type="text", inlines=[ContentInline(text="查看视频", url=url)])]
        if tag == "details":
            summary = node.find("summary")
            label = "".join(summary.itertext()).strip() if summary is not None else "展开内容"
            if summary is not None:
                node.remove(summary)
            return [CapturedBlock(type="details", text=label, children=self.flow(node, depth))]
        if tag == "table":
            rows = []
            for row in node.xpath("./tr|./thead/tr|./tbody/tr|./tfoot/tr"):
                cells = [
                    CapturedBlock(
                        type="table_cell",
                        header=cell.tag == "th",
                        children=self.flow(cell, depth + 2),
                    )
                    for cell in row
                    if cell.tag in ("td", "th")
                ]
                rows.append(CapturedBlock(type="table_row", children=cells))
            return [CapturedBlock(type="table", children=rows)]
        children = self.flow(node, depth)
        if tag in ("ul", "ol"):
            return [CapturedBlock(type="list", ordered=tag == "ol", children=children)]
        if tag == "li":
            return [CapturedBlock(type="list_item", children=children)]
        if tag == "blockquote":
            return [CapturedBlock(type="quote", children=children)]
        if re.fullmatch(r"h[1-6]", tag):
            for child in children:
                if child.type == "text":
                    child.type = "heading"
                    child.level = int(tag[1])
        return children


def parse_body(link: dict[str, Any]) -> tuple[str, list[str], list[CapturedBlock], list[str]]:
    value = link.get("text")
    try:
        raw = json.loads(value) if isinstance(value, str) else value
    except (ValueError, RecursionError):
        raw = None
    parser = ArticleParser()
    if not isinstance(raw, list):
        blocks = parser.fragment(text(value))
    else:
        blocks = []
        # HTML carries inline positions. Appended image blocks are its gallery inventory.
        html_images: set[tuple[str, str]] = set()
        for row in raw[:MAX_BLOCKS]:
            row = obj(row)
            kind = row.get("type")
            if kind in ("html", "text", "txt"):
                parsed = parser.fragment(text(row.get("text")))
                blocks.extend(parsed)
                if kind == "html":
                    html_images.update(media_key(url) for url in blocks_images(parsed))
            elif kind == "img":
                image = image_block(
                    row.get("url"),
                    row.get("text"),
                    width=row.get("width"),
                    height=row.get("height"),
                )
                if image and image.url and media_key(image.url) not in html_images:
                    blocks.append(image)
            elif kind == "game_card":
                blocks.append(game_block(row.get("appid")))
            else:
                parser.warn("文章包含暂未完整支持的内容块，已保留可读取的文字和链接。")
                blocks.extend(parser.fragment(text(row.get("text"))))
                url = article_url(text(row.get("url")))
                if url:
                    blocks.append(
                        CapturedBlock(
                            type="text", inlines=[ContentInline(text="查看原始内容", url=url)]
                        )
                    )
        if len(raw) > MAX_BLOCKS:
            parser.warn("正文内容块超过上限，已保留取得的内容；请查看原网页补充。")
    images = blocks_images(blocks)
    if len(images) > MAX_IMAGES:
        parser.warn("正文图片超过 1000 张，超出部分未载入。")
        allowed = set(images[:MAX_IMAGES])
        for block in walk_blocks(blocks):
            if block.type == "image" and block.url not in allowed:
                block.url = None
    return blocks_text(blocks), blocks_images(blocks), blocks, parser.warnings


def enrich_games(blocks: list[CapturedBlock], games: dict[str, dict[str, Any]]) -> bool:
    incomplete = False
    for block in walk_blocks(blocks):
        if block.type != "game_card":
            continue
        row = games.get(block.appid or "", {})
        if str(row.get("steam_appid", "")) != block.appid:
            incomplete = True
            continue
        block.text = text(row.get("name")) or "游戏卡片"
        block.image = media_url(row.get("image"))
        image = urlsplit(block.image or "")
        # Heybox's `steam_appid` also holds Epic IDs. Require explicit Steam
        # asset provenance from the official card response before building a URL.
        if (
            image.hostname == "heyboxbj.max-c.com"
            and image.path.startswith("/gameimg/steam_item_assets/")
            and row.get("game_type") == "pc"
        ):
            block.store = "steam"
            block.url = f"https://store.steampowered.com/app/{block.appid}/"
        elif image.hostname == "heyboxbj.max-c.com" and image.path.startswith(
            "/gameimg/epic_game_image/"
        ):
            block.store = "epic"
        else:
            incomplete = True
    return incomplete
