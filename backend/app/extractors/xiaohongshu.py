# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse HTML note data and collect bounded comments and replies via the read-only web API."""

import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from lxml import etree
from lxml import html as lxml_html
from pydantic import SecretStr

from app.extractors.base import CapturedComment, CapturedContent, ExtractionError
from app.extractors.generic import PlatformRequests, ScopedCookie, fetch_html
from app.extractors.xhs_api import XhsClient
from app.security.urls import UnsafeURL, normalize_url

COOKIE_HOSTS = frozenset({"www.xiaohongshu.com", "xiaohongshu.com"})
PAGE_HOSTS = COOKIE_HOSTS | {"xhslink.com", "www.xhslink.com", "xhslink.cn", "www.xhslink.cn"}
MAX_COMMENTS = 100
LOGIN_ERROR = "小红书登录态失效或未配置，请在设置中更新 Cookie 后重试"
STRUCTURE_ERROR = "未找到小红书帖子数据，页面结构可能已变化；请确认原始链接可访问并反馈适配问题"


def check_status(status: int) -> None:
    if status == 401:
        raise ExtractionError(LOGIN_ERROR, False)
    if status in (403, 461, 471):
        raise ExtractionError("小红书限制访问，请在浏览器完成验证并确认帖子可访问后重试", False)
    if status == 429:
        raise ExtractionError("小红书请求过于频繁，请稍后重试")
    if status in (404, 410):
        raise ExtractionError("小红书帖子不存在或已删除，请检查原始链接", False)


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _count(value: Any) -> int:
    # Abbreviated counts are not exact; do not invent values from labels such as "1万+".
    if type(value) is int or (isinstance(value, str) and value.isascii() and value.isdigit()):
        try:
            return min(max(int(value), 0), 2**31 - 1)
        except ValueError:
            pass
    return 0


def _published_at(value: Any) -> datetime | None:
    if type(value) not in (int, float) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000 if value >= 10**12 else value, tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def _image_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return normalize_url("https:" + value if value.startswith("//") else value)
    except UnsafeURL:
        return None


def _initial_state(tree: lxml_html.HtmlElement) -> dict[str, Any]:
    for script in tree.xpath("//script[not(@src)]/text()"):
        match = re.search(r"(?:^|[;\s])window\.__INITIAL_STATE__\s*=\s*", script)
        if not match:
            continue
        # The serialized state includes undefined and empty JS collections. Accept only
        # these literal forms; never evaluate page JavaScript or change quoted text.
        source = re.sub(
            r'"(?:\\.|[^"\\])*"|\bundefined\b|\bnew\s+(Map|Set)\s*\(\s*\[\s*\]\s*\)',
            lambda token: (
                "{}"
                if token[1] == "Map"
                else "[]" if token[1] == "Set" else "null" if token[0] == "undefined" else token[0]
            ),
            script[match.end() :],
        )
        try:
            value, _ = json.JSONDecoder().raw_decode(source)
            return _object(value)
        except (ValueError, RecursionError):
            continue
    return {}


def _comments(detail: dict[str, Any], max_comments: int) -> list[CapturedComment]:
    if max_comments == 0:
        return []
    rows = _object(detail.get("comments")).get("list", [])
    if not isinstance(rows, list):
        return []
    result: list[CapturedComment] = []
    seen_ids: set[str] = set()
    stack = [(row, None) for row in reversed(rows)]
    visited = 0
    while stack and len(result) < max_comments and visited < 10000:
        raw, parent = stack.pop()
        visited += 1
        row = _object(raw)
        text = _text(row.get("content"))
        identifier = _text(row.get("id"))[:200]
        children = row.get("subComments", row.get("sub_comments", []))
        if isinstance(children, list):
            stack.extend((child, identifier or parent) for child in reversed(children))
        if not text or (identifier and identifier in seen_ids):
            continue
        if identifier:
            seen_ids.add(identifier)
        user = _object(row.get("userInfo") or row.get("user_info"))
        target = _object(row.get("targetComment") or row.get("target_comment"))
        result.append(
            CapturedComment(
                source_id=identifier or None,
                parent_source_id=_text(target.get("id"))[:200] or parent,
                author=_text(user.get("nickname")) or None,
                content=text,
                likes=_count(row.get("likeCount", row.get("like_count"))),
                replies=_count(row.get("subCommentCount", row.get("sub_comment_count"))),
            )
        )
    return result


def parse_xiaohongshu(html: str, url: str, *, max_comments: int = MAX_COMMENTS) -> CapturedContent:
    if type(max_comments) is not int or not 0 <= max_comments <= MAX_COMMENTS:
        raise ValueError("Comment capture limit must be an integer between 0 and 100")
    parts = urlsplit(normalize_url(url))
    if parts.hostname not in COOKIE_HOSTS:
        raise ExtractionError("小红书短链接未跳转到帖子，请复制完整帖子链接重试", False)
    if parts.path.rstrip("/") in ("/login", "/website-login"):
        raise ExtractionError(LOGIN_ERROR, False)
    try:
        tree = lxml_html.fromstring(html)
    except (etree.ParserError, ValueError):
        raise ExtractionError(STRUCTURE_ERROR, False) from None
    state = _initial_state(tree)
    match = re.fullmatch(r"/(?:explore|discovery/item)/([a-zA-Z0-9]+)/?", parts.path)
    if match is None:
        raise ExtractionError("请使用小红书帖子链接，暂不支持个人主页或搜索页面", False)
    note_id = match[1]
    details = _object(_object(state.get("note")).get("noteDetailMap"))
    detail = _object(details.get(note_id))
    note = _object(detail.get("note"))
    # Never substitute a recommended note when the requested note is absent.
    if not note or (_text(note.get("noteId")) not in ("", note_id)):
        title = "".join(tree.xpath("//title/text()")).strip()
        if title in ("登录 - 小红书", "小红书 - 登录"):
            raise ExtractionError(LOGIN_ERROR, False)
        if title in ("安全验证", "小红书 - 安全验证"):
            raise ExtractionError("小红书要求安全验证，请在浏览器完成验证后重试", False)
        if title in ("访问频繁", "小红书 - 访问频繁"):
            raise ExtractionError("小红书请求过于频繁，请稍后重试")
        raise ExtractionError(STRUCTURE_ERROR, False)
    images: list[str] = []
    rows = note.get("imageList", [])
    if isinstance(rows, list):
        for row in rows[:50]:
            row = _object(row)
            image = _image_url(row.get("urlDefault")) or _image_url(row.get("urlPre"))
            if image and image not in images:
                images.append(image)
    title, text = _text(note.get("title")), _text(note.get("desc"))
    if not (title or text or images):
        raise ExtractionError(STRUCTURE_ERROR, False)
    user = _object(note.get("user"))
    user_id = _text(user.get("userId"))
    author_url = (
        f"https://www.xiaohongshu.com/user/profile/{user_id}"
        if re.fullmatch(r"[a-zA-Z0-9]+", user_id)
        else None
    )
    return CapturedContent(
        url=url,
        platform="xiaohongshu",
        title=title[:1000],
        text=text,
        author=_text(user.get("nickname")) or None,
        author_url=author_url,
        published_at=_published_at(note.get("time")),
        images=images,
        comments=_comments(detail, max_comments),
        comment_capture_limit=max_comments,
        extractor_version=3,
        raw_html=html,
    )


class XiaohongshuExtractor:
    name = "xiaohongshu"

    def __init__(
        self,
        cookie_loader: Callable[[str], SecretStr | None] | None = None,
        *,
        max_comments: int = MAX_COMMENTS,
    ) -> None:
        self.cookie_loader = cookie_loader
        self.max_comments = max_comments

    def matches(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and parts.hostname in PAGE_HOSTS

    def extract(self, url: str, payload: dict | None = None) -> CapturedContent:
        secret = self.cookie_loader(self.name) if self.cookie_loader else None
        requests = PlatformRequests()
        html, final_url = fetch_html(
            url,
            cookie=ScopedCookie(secret, COOKIE_HOSTS) if secret else None,
            allowed_hosts=PAGE_HOSTS,
            check_status=check_status,
            requests=requests,
        )
        content = parse_xiaohongshu(html, final_url, max_comments=self.max_comments)
        if len(content.comments) >= self.max_comments:
            return content
        parts = urlsplit(final_url)
        note_id = parts.path.rstrip("/").rsplit("/", 1)[-1]
        state = _initial_state(lxml_html.fromstring(html))
        detail = _object(_object(_object(state.get("note")).get("noteDetailMap")).get(note_id))
        embedded = _object(detail.get("comments"))
        token = parse_qs(parts.query).get("xsec_token", [""])[0]
        if not secret or not token:
            content.capture_warnings.append(
                "仅保存页面已有评论；补抓评论需配置完整 Cookie，并使用带访问参数的帖子链接。"
            )
            return content
        client = XhsClient(secret, requests)
        rows = embedded.get("list", [])
        rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        cursor = _text(embedded.get("cursor"))
        visited: set[str] = set()
        deadline = time.monotonic() + 180
        reply_budget = [10]
        self.collect_replies(content, rows, client, note_id, token, deadline, reply_budget)
        # API pagination may repeat rows or cursors; bound pages and elapsed time independently.
        top_complete = embedded.get("hasMore") is False or embedded.get("has_more") is False
        for _ in range(10):
            if top_complete or len(content.comments) >= self.max_comments:
                break
            if cursor in visited or time.monotonic() >= deadline:
                break
            visited.add(cursor)
            page = client.comments(note_id, token, cursor)
            comments = page.get("comments")
            if not isinstance(comments, list) or type(page.get("has_more")) is not bool:
                raise ExtractionError("小红书评论结构已变化，请反馈适配问题", False)
            additions = [row for row in comments if isinstance(row, dict)]
            rows.extend(additions)
            content.comments = _comments({"comments": {"list": rows}}, self.max_comments)
            self.collect_replies(content, rows, client, note_id, token, deadline, reply_budget)
            top_complete = page["has_more"] is False
            if len(content.comments) >= self.max_comments or top_complete:
                break
            cursor = _text(page.get("cursor"))
            if not cursor:
                break
        if not top_complete and len(content.comments) < self.max_comments:
            content.capture_warnings.append("评论分页提前结束，已保留取得的评论；可稍后重新采集。")
        return content

    def collect_replies(
        self,
        content: CapturedContent,
        rows: list[dict[str, Any]],
        client: XhsClient,
        note_id: str,
        token: str,
        deadline: float,
        budget: list[int] | None = None,
    ) -> None:
        budget = [10] if budget is None else budget
        for row in rows:
            root_id = _text(row.get("id"))
            children = row.get("subComments", row.get("sub_comments", []))
            children = list(children) if isinstance(children, list) else []
            count = _count(row.get("subCommentCount", row.get("sub_comment_count")))
            more = row.get("subCommentHasMore", row.get("sub_comment_has_more"))
            if not root_id or more is False or count <= len(children):
                continue
            cursor = _text(row.get("subCommentCursor", row.get("sub_comment_cursor")))
            visited: set[str] = set()
            try:
                while len(content.comments) < self.max_comments:
                    if budget[0] <= 0 or time.monotonic() >= deadline or cursor in visited:
                        content.capture_warnings.append(
                            "部分楼中楼回复未完整取得，已保留采集结果。"
                        )
                        return
                    visited.add(cursor)
                    budget[0] -= 1
                    page = client.replies(note_id, root_id, token, cursor)
                    additions = page.get("comments")
                    if not isinstance(additions, list) or type(page.get("has_more")) is not bool:
                        raise ExtractionError("小红书回复结构无法识别", False)
                    children.extend(additions)
                    row["subComments"] = children
                    content.comments = _comments({"comments": {"list": rows}}, self.max_comments)
                    if not page["has_more"]:
                        row["subCommentHasMore"] = False
                        break
                    cursor = _text(page.get("cursor"))
                    if not cursor:
                        raise ExtractionError("小红书回复分页游标缺失", False)
            except ExtractionError:
                content.capture_warnings.append("部分楼中楼回复未完整取得，已保留采集结果。")
                return
