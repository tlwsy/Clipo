# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse public YouTube player state, available captions and bounded top comments."""

import json
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from lxml import etree
from lxml import html as lxml_html

from app.extractors.base import CapturedComment, CapturedContent, ExtractionError
from app.extractors.generic import PlatformRequests, fetch_html, fetch_json
from app.extractors.structured import count, media_url, obj, script_object, text

PAGE_HOSTS = frozenset({"www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be"})
API_HOSTS = frozenset({"www.youtube.com"})
CAPTION_HOSTS = frozenset({"www.youtube.com", "youtube.com", "video.google.com"})


def video_id(url: str) -> str:
    parts = urlsplit(url)
    identifier = ""
    if parts.hostname == "youtu.be":
        identifier = parts.path.strip("/")
    elif parts.hostname in PAGE_HOSTS and parts.path == "/watch":
        values = parse_qs(parts.query).get("v", [])
        if len(values) == 1:
            identifier = values[0]
    elif parts.hostname in PAGE_HOSTS:
        match = re.fullmatch(r"/(?:shorts|live|embed)/([\w-]{11})/?", parts.path, re.ASCII)
        if match:
            identifier = match[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", identifier):
        raise ExtractionError("请使用 YouTube 单个视频链接，暂不支持播放列表或频道", False)
    return identifier


def nodes(value: Any, *, skip_replies: bool = False) -> Iterator[dict[str, Any]]:
    stack = [value]
    visited = 0
    while stack and visited < 50000:
        item = stack.pop()
        visited += 1
        if isinstance(item, dict):
            yield item
            stack.extend(
                reversed(
                    [
                        v
                        for k, v in item.items()
                        if not skip_replies
                        or k not in ("replies", "commentRepliesRenderer", "subThreads")
                    ]
                )
            )
        elif isinstance(item, list):
            stack.extend(reversed(item))


def runs(value: Any) -> str:
    value = obj(value)
    if isinstance(value.get("simpleText"), str):
        return text(value["simpleText"])
    items = value.get("runs", [])
    return (
        "".join(obj(row)["text"] for row in items if isinstance(obj(row).get("text"), str)).strip()
        if isinstance(items, list)
        else ""
    )


def exact_count(value: Any) -> int:
    if type(value) is int:
        return count(value)
    value = text(value)
    # Abbreviated labels such as 1.2K are not exact counts and remain unset (zero).
    match = re.fullmatch(r"([0-9]+(?:,[0-9]{3})*)(?:\s+(?:likes?|replies))?", value, re.I)
    return count(match[1].replace(",", "")) if match else 0


def config_object(html: str) -> dict[str, Any]:
    try:
        tree = lxml_html.fromstring(html)
    except (etree.ParserError, ValueError):
        return {}
    result = {}
    for script in tree.xpath("//script[not(@src)]/text()"):
        for match in re.finditer(r"(?:^|[;\s])ytcfg\.set\(\s*", script):
            try:
                value, _ = json.JSONDecoder().raw_decode(script[match.end() :])
                result.update(obj(value))
            except (ValueError, RecursionError):
                continue
    return result


def check_status(status: int) -> None:
    if status in (401, 403):
        raise ExtractionError("YouTube 要求登录或访问验证，请在浏览器确认视频可访问后重试", False)
    if status == 429:
        raise ExtractionError("YouTube 请求过于频繁，请稍后重试")
    if status in (404, 410):
        raise ExtractionError("YouTube 视频不存在或已删除，请检查链接", False)


def comments_root(data: dict[str, Any]) -> list[dict[str, Any]]:
    sections = []
    for node in nodes(data):
        section = obj(node.get("itemSectionRenderer"))
        if (
            section.get("sectionIdentifier") == "comment-item-section"
            or section.get("targetId") == "comments-section"
        ):
            sections.append(section)
        panel = obj(node.get("engagementPanelSectionListRenderer"))
        if panel.get("targetId") == "engagement-panel-comments-section":
            sections.append(panel.get("content", {}))
    return sections


def continuation(root: Any) -> str:
    for node in nodes(root, skip_replies=True):
        item = obj(node.get("continuationItemRenderer"))
        endpoint = obj(item.get("continuationEndpoint"))
        token = text(obj(endpoint.get("continuationCommand")).get("token"))
        if token:
            return token
    return ""


def top_sort(root: Any) -> tuple[bool, str] | None:
    for node in nodes(root, skip_replies=True):
        items = obj(node.get("sortFilterSubMenuRenderer")).get("subMenuItems")
        if isinstance(items, list) and items:
            first = obj(items[0])
            endpoint = obj(first.get("serviceEndpoint"))
            return first.get("selected") is True, text(
                obj(endpoint.get("continuationCommand")).get("token")
            )
    return None


class YoutubeExtractor:
    name = "youtube"

    def __init__(self, *, max_comments: int = 100) -> None:
        self.max_comments = max_comments

    def matches(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and parts.hostname in PAGE_HOSTS

    def extract(self, url: str, payload: dict | None = None) -> CapturedContent:
        identifier = video_id(url)
        requests = PlatformRequests()
        # Canonical watch pages expose the same video without relying on Shorts UI scripts.
        canonical = "https://www.youtube.com/watch?" + urlencode({"v": identifier, "hl": "en"})
        html, final_url = fetch_html(
            canonical, allowed_hosts=PAGE_HOSTS, requests=requests, check_status=check_status
        )
        if video_id(final_url) != identifier:
            raise ExtractionError("YouTube 返回其他视频，请重新复制链接", False)
        player = script_object(html, "ytInitialPlayerResponse")
        details = obj(player.get("videoDetails"))
        status = obj(player.get("playabilityStatus")).get("status")
        if status in ("LOGIN_REQUIRED", "AGE_CHECK_REQUIRED", "CONTENT_CHECK_REQUIRED"):
            raise ExtractionError(
                "YouTube 视频需要登录或年龄验证，当前只支持公开可读取的视频", False
            )
        if status not in (None, "OK"):
            raise ExtractionError("YouTube 视频当前不可读取，请在浏览器确认地区或访问限制", False)
        if details.get("videoId") != identifier or not text(details.get("title")):
            raise ExtractionError("YouTube 视频结构无法识别，请反馈适配问题", False)
        micro = obj(obj(player.get("microformat")).get("playerMicroformatRenderer"))
        published = None
        try:
            published = datetime.fromisoformat(text(micro.get("publishDate"))).replace(tzinfo=UTC)
        except ValueError:
            pass
        thumbnails = obj(details.get("thumbnail")).get("thumbnails", [])
        images = (
            [image for row in thumbnails if (image := media_url(obj(row).get("url")))]
            if isinstance(thumbnails, list)
            else []
        )
        channel = text(details.get("channelId"))
        content = CapturedContent(
            url=final_url,
            platform=self.name,
            title=text(details.get("title"))[:1000],
            text=text(details.get("shortDescription")),
            author=text(details.get("author")) or None,
            author_url=(
                f"https://www.youtube.com/channel/{channel}"
                if re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel)
                else None
            ),
            published_at=published,
            images=images[-1:],
            raw_html=html,
            comment_capture_limit=self.max_comments,
            extractor_version=1,
        )
        self.captions(content, identifier, player, requests)
        if self.max_comments:
            self.comments(
                content, script_object(html, "ytInitialData"), config_object(html), requests
            )
        return content

    def captions(
        self,
        content: CapturedContent,
        identifier: str,
        player: dict[str, Any],
        requests: PlatformRequests,
    ) -> None:
        try:
            tracks = obj(obj(player.get("captions")).get("playerCaptionsTracklistRenderer")).get(
                "captionTracks", []
            )
            tracks = (
                [obj(t) for t in tracks if text(obj(t).get("baseUrl"))]
                if isinstance(tracks, list)
                else []
            )
            if not tracks:
                content.capture_warnings.append("YouTube 未提供公开可取得的字幕，已保存视频简介。")
                return
            tracks.sort(
                key=lambda t: (
                    not text(t.get("languageCode")).startswith("zh"),
                    not text(t.get("languageCode")).startswith("en"),
                    t.get("kind") == "asr",
                )
            )
            track = tracks[0]
            url = media_url(track.get("baseUrl"))
            if not url:
                raise ExtractionError("字幕链接无法识别", False)
            parts = urlsplit(url)
            params = parse_qs(parts.query, keep_blank_values=True)
            if (
                parts.scheme != "https"
                or parts.hostname not in CAPTION_HOSTS
                or parts.path not in ("/api/timedtext", "/timedtext")
                or params.get("v") != [identifier]
            ):
                raise ExtractionError("字幕链接与视频或官方主机不符，请反馈适配问题", False)
            params["fmt"] = ["json3"]
            response = fetch_json(
                urlunsplit(parts._replace(query=urlencode(params, doseq=True))),
                allowed_hosts=CAPTION_HOSTS,
                requests=requests,
                check_status=check_status,
            )
            events = response.get("events")
            if not isinstance(events, list):
                raise ExtractionError("字幕结构无法识别", False)
            lines = []
            for event in events:
                segments = obj(event).get("segs", [])
                if isinstance(segments, list):
                    line = "".join(
                        obj(s).get("utf8", "")
                        for s in segments
                        if isinstance(obj(s).get("utf8"), str)
                    ).strip()
                    if line:
                        lines.append(line)
            transcript = "\n".join(lines)
            if not transcript:
                raise ExtractionError("字幕接口未返回文本", False)
            if len(transcript) > 200000:
                transcript = transcript[:200000]
                content.capture_warnings.append("字幕超过保存长度上限，仅保留前 200000 字符。")
            label = text(track.get("languageCode"))
            label += "，自动字幕" if track.get("kind") == "asr" else ""
            content.text = "\n\n".join(
                part for part in (content.text, f"字幕（{label}）\n{transcript}") if part
            )
        except ExtractionError as exc:
            content.capture_warnings.append(f"未取得 YouTube 字幕：{exc}；视频简介已保存。")

    def next_page(
        self, token: str, config: dict[str, Any], requests: PlatformRequests
    ) -> dict[str, Any]:
        client = obj(obj(config.get("INNERTUBE_CONTEXT")).get("client"))
        version = text(client.get("clientVersion") or config.get("INNERTUBE_CLIENT_VERSION"))
        if not re.fullmatch(r"[0-9.]{1,80}", version) or len(token) > 16384:
            raise ExtractionError("YouTube 评论请求参数缺失或变化，请反馈适配问题", False)
        safe_client = {"clientName": "WEB", "clientVersion": version, "hl": "en", "gl": "US"}
        visitor = text(client.get("visitorData"))
        if (
            visitor
            and len(visitor) <= 4096
            and visitor.isascii()
            and not any(ord(c) < 32 for c in visitor)
        ):
            safe_client["visitorData"] = visitor
        response = fetch_json(
            "https://www.youtube.com/youtubei/v1/next?prettyPrint=false",
            allowed_hosts=API_HOSTS,
            requests=requests,
            check_status=check_status,
            headers={
                "Origin": "https://www.youtube.com",
                "Referer": "https://www.youtube.com/",
                "X-Youtube-Client-Name": "1",
                "X-Youtube-Client-Version": version,
            },
            json_body={"context": {"client": safe_client}, "continuation": token},
        )
        if response.get("error"):
            raise ExtractionError("YouTube 评论接口拒绝访问，请稍后重试", False)
        return response

    def append_comments(
        self, content: CapturedContent, root: Any, response: dict[str, Any], seen: set[str]
    ) -> None:
        mutations = obj(obj(response.get("frameworkUpdates")).get("entityBatchUpdate")).get(
            "mutations", []
        )
        entities = (
            {
                text(obj(row).get("entityKey")): obj(obj(row).get("payload")).get(
                    "commentEntityPayload", {}
                )
                for row in mutations
            }
            if isinstance(mutations, list)
            else {}
        )
        for node in nodes(root, skip_replies=True):
            thread = obj(node.get("commentThreadRenderer"))
            if not thread:
                continue
            old = obj(obj(thread.get("comment")).get("commentRenderer"))
            if old:
                key = text(old.get("commentId"))
                body = runs(old.get("contentText"))
                author = runs(old.get("authorText"))
                likes = exact_count(runs(old.get("voteCount")))
                replies = count(old.get("replyCount"))
            else:
                vm = obj(thread.get("commentViewModel"))
                vm = obj(vm.get("commentViewModel")) or vm
                entity = obj(entities.get(text(vm.get("commentKey"))))
                if not entity:
                    raise ExtractionError("YouTube 评论结构无法识别，请反馈适配问题", False)
                properties = obj(entity.get("properties"))
                key = text(properties.get("commentId"))
                body = text(obj(properties.get("content")).get("content"))
                author = text(obj(entity.get("author")).get("displayName"))
                likes = exact_count(obj(entity.get("toolbar")).get("likeCountA11y"))
                replies = count(vm.get("replyCount"))
            if not key or not body or key in seen:
                continue
            seen.add(key)
            content.comments.append(
                CapturedComment(author=author or None, content=body, likes=likes, replies=replies)
            )
            if len(content.comments) >= self.max_comments:
                return

    def comments(
        self,
        content: CapturedContent,
        data: dict[str, Any],
        config: dict[str, Any],
        requests: PlatformRequests,
    ) -> None:
        root = comments_root(data)
        response = data
        seen: set[str] = set()
        visited: set[str] = set()
        sorted_top = False
        deadline = time.monotonic() + 180
        if not root:
            content.capture_warnings.append(
                "YouTube 页面未提供可读取的评论入口，评论可能关闭或需要登录。"
            )
            return
        try:
            for _ in range(11):
                sort = top_sort(root)
                token = ""
                if sort and not sorted_top:
                    sorted_top = True
                    if not sort[0]:
                        token = sort[1]
                    if not sort[0] and not token:
                        raise ExtractionError("无法切换 YouTube 热评排序，请反馈适配问题", False)
                if not token:
                    self.append_comments(content, root, response, seen)
                    if len(content.comments) >= self.max_comments:
                        return
                    token = continuation(root)
                if not token:
                    return
                if token in visited or len(visited) >= 10 or time.monotonic() >= deadline:
                    break
                visited.add(token)
                response = self.next_page(token, config, requests)
                items = []
                for node in nodes(response):
                    for key in ("reloadContinuationItemsCommand", "appendContinuationItemsAction"):
                        batch = obj(node.get(key)).get("continuationItems")
                        if isinstance(batch, list):
                            items.extend(batch)
                if not items:
                    raise ExtractionError("YouTube 评论响应结构无法识别，请反馈适配问题", False)
                root = items
            content.capture_warnings.append("YouTube 热评分页提前结束，已保留取得的评论。")
        except ExtractionError as exc:
            content.capture_warnings.append(f"YouTube 热评未完整取得：{exc}；已有内容已保存。")
