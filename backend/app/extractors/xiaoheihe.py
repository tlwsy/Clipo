# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read Heybox posts and paginated comments and embedded replies via its official web API."""

import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from pydantic import SecretStr

from app.content import blocks_text, walk_blocks
from app.extractors.base import (
    CapturedComment,
    CapturedContent,
    ExtractionError,
    LoginExpiredError,
)
from app.extractors.generic import PlatformRequests, ScopedCookie, fetch_html, fetch_json
from app.extractors.heybox_content import enrich_games, parse_body, readable_emojis
from app.extractors.heybox_sign import sign_params
from app.extractors.structured import count, html_text, obj, text, timestamp

API_HOSTS = frozenset({"api.xiaoheihe.cn"})
PAGE_HOSTS = API_HOSTS | {"www.xiaoheihe.cn", "xiaoheihe.cn"}
TREE_PATH = "/bbs/app/link/tree"
GAME_INFO_PATH = "/game/get_game_infos/"
LOGIN_ERROR = "小黑盒登录态失效，请在设置中更新完整 Cookie 后重试"
STRUCTURE_ERROR = "小黑盒帖子结构无法识别，请确认帖子可访问并反馈适配问题"


def link_id(url: str) -> str:
    parts = urlsplit(url)
    identifier = ""
    if parts.hostname in PAGE_HOSTS - API_HOSTS:
        match = re.fullmatch(r"/app/bbs/link/([a-zA-Z0-9]+)/?", parts.path)
        identifier = match[1] if match else ""
    elif parts.hostname in API_HOSTS and parts.path.rstrip("/") == "/v3/bbs/app/api/web/share":
        ids = parse_qs(parts.query).get("link_id", [])
        identifier = ids[0] if len(ids) == 1 else ""
    if not re.fullmatch(r"[a-zA-Z0-9]{1,80}", identifier):
        raise ExtractionError("请使用小黑盒帖子链接或官方帖子分享链接", False)
    return identifier


def check_status(status: int) -> None:
    if status == 401:
        raise LoginExpiredError(LOGIN_ERROR)
    if status in (403, 412):
        raise ExtractionError("小黑盒限制访问，请在浏览器完成验证后重试", False)
    if status == 429:
        raise ExtractionError("小黑盒请求过于频繁，请稍后重试")
    if status in (404, 410):
        raise ExtractionError("小黑盒帖子不存在或已删除，请检查链接", False)


class HeyboxClient:
    def __init__(self, secret: SecretStr | None, requests: PlatformRequests | None = None) -> None:
        self.cookie = ScopedCookie(secret, API_HOSTS) if secret else None
        self.requests = requests or PlatformRequests()

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if path not in (TREE_PATH, "/account/restore_login", GAME_INFO_PATH):
            raise ValueError("Unsupported Heybox endpoint")
        query = {
            "os_type": "web",
            "app": "heybox",
            "client_type": "web",
            "version": "999.0.4",
            "web_version": "2.5",
            "x_client_type": "web",
            "x_app": "heybox_website",
            "x_os_type": "Windows",
            "device_info": "Chrome",
            **params,
            **sign_params(path),
        }
        response = fetch_json(
            "https://api.xiaoheihe.cn" + path + "?" + urlencode(query),
            cookie=self.cookie,
            allowed_hosts=API_HOSTS,
            headers={"Origin": "https://www.xiaoheihe.cn", "Referer": "https://www.xiaoheihe.cn/"},
            check_status=check_status,
            requests=self.requests,
        )
        status = response.get("status")
        if status in ("login", "relogin"):
            raise LoginExpiredError(LOGIN_ERROR)
        if status in ("show_captcha", "need_google_check", "lack_token"):
            raise ExtractionError(
                "小黑盒需要登录或设备验证，请在浏览器完成验证并更新完整 Cookie", False
            )
        if status != "ok" or not isinstance(response.get("result"), dict):
            raise ExtractionError("小黑盒接口未返回可用数据，请检查链接或反馈适配问题", False)
        return response["result"]

    def page(self, identifier: str, page: int, limit: int) -> dict[str, Any]:
        return self.get(
            TREE_PATH,
            {
                "link_id": identifier,
                "is_first": "1" if page == 1 else "0",
                "page": str(page),
                "index": "1",
                "limit": str(limit),
                "owner_only": "0",
            },
        )

    def check_login(self) -> bool:
        result = self.get("/account/restore_login", {})
        user_id = obj(result.get("profile")).get("heybox_id") or obj(
            result.get("account_detail")
        ).get("userid")
        if user_id and text(result.get("pkey")):
            return True
        raise ExtractionError("小黑盒未返回明确的登录状态，请重新登录后更新 Cookie", False)

    def game_infos(self, appids: list[str]) -> dict[str, dict[str, Any]]:
        if not appids:
            return {}
        result = self.get(GAME_INFO_PATH, {"appids": ",".join(appids)})
        rows = result.get("base_infos")
        if not isinstance(rows, list):
            return {}
        return {
            str(row.get("steam_appid")): row
            for row in rows
            if isinstance(row, dict) and row.get("steam_appid") is not None
        }


def parse_heybox(
    result: dict[str, Any],
    url: str,
    html: str,
    max_comments: int,
    games: dict[str, dict[str, Any]] | None = None,
) -> CapturedContent:
    link = obj(result.get("link"))
    if not link:
        raise ExtractionError(STRUCTURE_ERROR, False)
    title = text(link.get("title"))
    body, images, blocks, warnings = parse_body(link)
    if games is not None:
        if enrich_games(blocks, games):
            warnings.append("部分游戏卡片未取得可靠商店信息，已保留原始卡片。")
        body = blocks_text(blocks)
    if not (title or body or images):
        raise ExtractionError(STRUCTURE_ERROR, False)
    user = obj(link.get("user"))
    user_id = str(user.get("userid", ""))
    return CapturedContent(
        url=url,
        platform="xiaoheihe",
        title=readable_emojis(title[:1000]),
        text=body,
        images=images,
        blocks=blocks,
        author=text(user.get("username")) or None,
        author_url=(
            f"https://www.xiaoheihe.cn/app/user/profile/{user_id}"
            if re.fullmatch(r"\d+", user_id)
            else None
        ),
        published_at=timestamp(link.get("create_at")),
        raw_html=html,
        comment_capture_limit=max_comments,
        extractor_version=3,
        capture_warnings=warnings,
    )


def _append_comments(
    content: CapturedContent,
    result: dict[str, Any],
    seen: set[str],
    limit: int,
) -> None:
    if not limit:
        return
    rows = result.get("comments", [])
    if not isinstance(rows, list):
        raise ExtractionError("小黑盒评论结构已变化，请反馈适配问题", False)
    for group in rows:
        if len(content.comments) >= limit:
            break
        floor = obj(group).get("comment")
        if not isinstance(floor, list) or not floor:
            continue
        root_id = str(obj(floor[0]).get("commentid", ""))[:200]
        for item_index, raw in enumerate(floor):
            if len(content.comments) >= limit:
                break
            row = obj(raw)
            identifier = str(row.get("commentid", ""))
            body = html_text(text(row.get("text")))
            key = identifier or body
            if not body or key in seen:
                continue
            seen.add(key)
            content.comments.append(
                CapturedComment(
                    source_id=identifier[:200] or None,
                    parent_source_id=root_id if item_index > 0 else None,
                    author=text(obj(row.get("user")).get("username")) or None,
                    content=body,
                    likes=count(row.get("up")),
                    replies=count(row.get("child_num", row.get("reply_num"))),
                )
            )
            nested = row.get("children", row.get("replies", []))
            if isinstance(nested, list) and item_index == 0:
                for child in nested:
                    if len(content.comments) >= limit:
                        break
                    child = obj(child)
                    child_id = str(child.get("commentid", ""))
                    child_text = html_text(text(child.get("text")))
                    child_key = child_id or child_text
                    if not child_text or child_key in seen:
                        continue
                    seen.add(child_key)
                    content.comments.append(
                        CapturedComment(
                            source_id=child_id[:200] or None,
                            parent_source_id=identifier[:200] or root_id or None,
                            author=text(obj(child.get("user")).get("username")) or None,
                            content=child_text,
                            likes=count(child.get("up")),
                        )
                    )


class XiaoheiheExtractor:
    name = "xiaoheihe"

    def __init__(
        self,
        cookie_loader: Callable[[str], SecretStr | None] | None = None,
        *,
        max_comments: int = 100,
    ) -> None:
        self.cookie_loader = cookie_loader
        self.max_comments = max_comments

    def matches(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and parts.hostname in PAGE_HOSTS

    def extract(self, url: str, payload: dict | None = None) -> CapturedContent:
        identifier = link_id(url)
        secret = self.cookie_loader(self.name) if self.cookie_loader else None
        requests = PlatformRequests()
        html, final_url = fetch_html(
            url,
            cookie=ScopedCookie(secret, PAGE_HOSTS) if secret else None,
            allowed_hosts=PAGE_HOSTS,
            check_status=check_status,
            requests=requests,
        )
        if link_id(final_url) != identifier:
            raise ExtractionError("小黑盒分享链接跳转到其他帖子，请复制完整帖子链接", False)
        client = HeyboxClient(secret, requests)
        first = client.page(identifier, 1, 20 if self.max_comments else 0)
        link = obj(first.get("link"))
        if str(link.get("linkid", "")) != identifier:
            # Share IDs are opaque and differ from numeric link IDs. Verify the API's
            # canonical share URL points back to the exact requested opaque identifier.
            try:
                same_share = link_id(text(link.get("share_url"))) == identifier
            except ExtractionError:
                same_share = False
            if not same_share:
                raise ExtractionError(STRUCTURE_ERROR, False)
        content = parse_heybox(first, final_url, html, self.max_comments)
        appids = list(
            dict.fromkeys(
                block.appid
                for block in walk_blocks(content.blocks)
                if block.type == "game_card" and block.appid
            )
        )
        if appids:
            try:
                games = client.game_infos(appids[:50])
                if enrich_games(content.blocks, games) or len(appids) > 50:
                    content.capture_warnings.append(
                        "部分游戏卡片未取得可靠商店信息，已保留原始卡片。"
                    )
            except ExtractionError:
                content.capture_warnings.append("游戏卡片详情暂时无法取得，正文和图片已保留。")
            content.text = blocks_text(content.blocks)
        seen: set[str] = set()
        page = first
        deadline = time.monotonic() + 180
        for number in range(1, 11):
            _append_comments(content, page, seen, self.max_comments)
            if len(content.comments) >= self.max_comments or page.get("has_more_floors") not in (
                True,
                1,
                "1",
            ):
                return content
            if number == 10 or time.monotonic() >= deadline:
                break
            page = client.page(identifier, number + 1, 20)
        content.capture_warnings.append("评论分页提前结束，已保留取得的评论；可稍后重新采集。")
        return content
