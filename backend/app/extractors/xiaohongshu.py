"""Parse note data embedded in HTML without executing JavaScript or calling signed APIs."""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from lxml import etree
from lxml import html as lxml_html
from pydantic import SecretStr

from app.extractors.base import CapturedComment, CapturedContent, ExtractionError
from app.extractors.generic import ScopedCookie, fetch_html
from app.security.urls import UnsafeURL, normalize_url

COOKIE_HOSTS = frozenset({"www.xiaohongshu.com", "xiaohongshu.com"})
PAGE_HOSTS = COOKIE_HOSTS | {"xhslink.com", "www.xhslink.com"}
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
        # XHS state uses bare undefined values. Preserve strings (including escaped quotes).
        source = re.sub(
            r'"(?:\\.|[^"\\])*"|\bundefined\b',
            lambda token: "null" if token[0] == "undefined" else token[0],
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
    result = []
    seen_ids: set[str] = set()
    for row in rows:
        row = _object(row)
        text = _text(row.get("content"))
        identifier = _text(row.get("id"))
        if not text or (identifier and identifier in seen_ids):
            continue
        if identifier:
            seen_ids.add(identifier)
        user = _object(row.get("userInfo") or row.get("user_info"))
        result.append(
            CapturedComment(
                author=_text(user.get("nickname")) or None,
                content=text,
                likes=_count(row.get("likeCount", row.get("like_count"))),
                replies=_count(row.get("subCommentCount", row.get("sub_comment_count"))),
            )
        )
        if len(result) == max_comments:
            break
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
        html, final_url = fetch_html(
            url,
            cookie=ScopedCookie(secret, COOKIE_HOSTS) if secret else None,
            allowed_hosts=PAGE_HOSTS,
            check_status=check_status,
        )
        return parse_xiaohongshu(html, final_url, max_comments=self.max_comments)
