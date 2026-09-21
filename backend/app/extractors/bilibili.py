"""Public Bilibili video metadata, available captions and bounded hot comments."""

import re
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from app.extractors.base import CapturedComment, CapturedContent, ExtractionError
from app.extractors.generic import PlatformRequests, fetch_html, fetch_json
from app.extractors.structured import count, media_url, obj, script_object, text, timestamp

PAGE_HOSTS = frozenset({"www.bilibili.com", "bilibili.com", "m.bilibili.com", "b23.tv"})
API_HOSTS = frozenset({"api.bilibili.com"})
CAPTION_HOSTS = frozenset({"aisubtitle.hdslb.com", "i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com"})


def identifier(value: Any) -> str:
    value = str(value) if type(value) is int else text(value)
    return value if re.fullmatch(r"[1-9][0-9]{0,18}", value) else ""


def video_params(url: str) -> tuple[dict[str, str], int]:
    parts = urlsplit(url)
    match = re.fullmatch(r"/video/(BV[0-9A-Za-z]{10}|av[1-9][0-9]{0,18})/?", parts.path)
    if parts.hostname not in PAGE_HOSTS - {"b23.tv"} or not match:
        raise ExtractionError("请使用 B 站视频链接或 b23.tv 分享链接", False)
    query = parse_qs(parts.query, keep_blank_values=True)
    pages = query.get("p", ["1"])
    if len(pages) != 1 or not re.fullmatch(r"[1-9][0-9]{0,3}", pages[0]):
        raise ExtractionError("B 站分 P 参数无效，请重新复制视频链接", False)
    return ({"bvid": match[1]} if match[1].startswith("BV") else {"aid": match[1][2:]}), int(
        pages[0]
    )


def check_status(status: int) -> None:
    if status in (401, 403, 412):
        raise ExtractionError("B 站限制访问，请在浏览器确认视频可访问后稍后重试", False)
    if status == 429:
        raise ExtractionError("B 站请求过于频繁，请稍后重试")
    if status in (404, 410):
        raise ExtractionError("B 站视频不存在或已删除，请检查链接", False)


class BilibiliExtractor:
    name = "bilibili"

    def __init__(self, *, max_comments: int = 100) -> None:
        self.max_comments = max_comments

    def matches(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and parts.hostname in PAGE_HOSTS

    def api(self, path: str, params: dict[str, str], requests: PlatformRequests) -> dict[str, Any]:
        response = fetch_json(
            "https://api.bilibili.com" + path + "?" + urlencode(params),
            allowed_hosts=API_HOSTS,
            requests=requests,
            check_status=check_status,
            headers={"Referer": "https://www.bilibili.com/"},
        )
        if response.get("code") == -101:
            raise ExtractionError("B 站此内容需要登录，当前只支持公开可读取的视频内容", False)
        if response.get("code") in (-352, -412, -403):
            raise ExtractionError("B 站要求访问验证，请在浏览器确认内容可访问后稍后重试", False)
        if response.get("code") in (-404, 62002):
            raise ExtractionError("B 站视频不存在或不可访问，请检查链接", False)
        if response.get("code") != 0 or not isinstance(response.get("data"), dict):
            raise ExtractionError("B 站接口未返回可用数据，请稍后重试或反馈适配问题", False)
        return response["data"]

    def extract(self, url: str, payload: dict | None = None) -> CapturedContent:
        requests = PlatformRequests()
        short = urlsplit(url).hostname == "b23.tv"
        requested = None if short else video_params(url)
        html, final_url = fetch_html(
            url, allowed_hosts=PAGE_HOSTS, requests=requests, check_status=check_status
        )
        params, page_number = video_params(final_url)
        if requested is not None and requested != (params, page_number):
            raise ExtractionError("B 站链接跳转到其他视频或分 P，请重新复制链接", False)
        data = obj(script_object(html, "__INITIAL_STATE__").get("videoData"))
        if not data:
            data = self.api("/x/web-interface/view", params, requests)
        if any(str(data.get(key, "")) != value for key, value in params.items()):
            raise ExtractionError("B 站返回的视频与链接不符，请重新复制链接", False)
        aid = identifier(data.get("aid"))
        pages = data.get("pages", [])
        pages = [obj(row) for row in pages] if isinstance(pages, list) else []
        page = next((row for row in pages if row.get("page") == page_number), {})
        cid = identifier(page.get("cid") or (data.get("cid") if page_number == 1 else None))
        if not aid or not cid or not text(data.get("title")):
            raise ExtractionError("B 站视频或分 P 信息缺失，请检查链接并反馈适配问题", False)
        owner = obj(data.get("owner"))
        mid = identifier(owner.get("mid"))
        image = media_url(data.get("pic"))
        content = CapturedContent(
            url=final_url,
            platform=self.name,
            title=text(data.get("title"))[:1000],
            text=text(data.get("desc")),
            author=text(owner.get("name")) or None,
            author_url=f"https://space.bilibili.com/{mid}" if mid else None,
            published_at=timestamp(data.get("pubdate")),
            images=[image] if image else [],
            raw_html=html,
            comment_capture_limit=self.max_comments,
            extractor_version=1,
        )
        self.captions(content, aid, cid, requests)
        if self.max_comments:
            self.comments(content, aid, requests)
        return content

    def captions(
        self, content: CapturedContent, aid: str, cid: str, requests: PlatformRequests
    ) -> None:
        try:
            data = self.api("/x/player/wbi/v2", {"aid": aid, "cid": cid}, requests)
            tracks = obj(data.get("subtitle")).get("subtitles", [])
            if not isinstance(tracks, list):
                raise ExtractionError("字幕结构无法识别，请反馈适配问题", False)
            tracks = [obj(track) for track in tracks if text(obj(track).get("subtitle_url"))]
            if not tracks:
                content.capture_warnings.append(
                    "字幕需要登录，已保存视频简介。"
                    if data.get("need_login_subtitle")
                    else "视频未提供公开可取得的字幕，已保存简介。"
                )
                return
            # Prefer Chinese, then English; retain the supplied language label.
            tracks.sort(
                key=lambda track: (
                    not text(track.get("lan")).startswith("zh"),
                    not text(track.get("lan")).startswith("en"),
                )
            )
            track = tracks[0]
            url = media_url(track.get("subtitle_url"))
            if (
                not url
                or urlsplit(url).scheme != "https"
                or urlsplit(url).hostname not in CAPTION_HOSTS
            ):
                raise ExtractionError("字幕链接不属于支持的官方主机，请反馈适配问题", False)
            response = fetch_json(url, allowed_hosts=CAPTION_HOSTS, requests=requests)
            rows = response.get("body")
            if not isinstance(rows, list):
                raise ExtractionError("字幕结构无法识别，请反馈适配问题", False)
            transcript = "\n".join(
                text(obj(row).get("content")) for row in rows if text(obj(row).get("content"))
            )
            if not transcript:
                raise ExtractionError("字幕接口未返回文本，请稍后重试", False)
            if len(transcript) > 200000:
                transcript = transcript[:200000]
                content.capture_warnings.append("字幕超过保存长度上限，仅保留前 200000 字符。")
            label = text(track.get("lan_doc")) or text(track.get("lan"))
            content.text = "\n\n".join(
                part for part in (content.text, f"字幕（{label}）\n{transcript}") if part
            )
        except ExtractionError as exc:
            content.capture_warnings.append(f"未取得字幕：{exc}；视频简介已保存。")

    def comments(self, content: CapturedContent, aid: str, requests: PlatformRequests) -> None:
        seen: set[str] = set()
        deadline = time.monotonic() + 180
        try:
            for page in range(1, 6):
                data = self.api(
                    "/x/v2/reply",
                    {"oid": aid, "type": "1", "sort": "2", "pn": str(page), "ps": "20"},
                    requests,
                )
                rows = data.get("replies")
                if rows is None:
                    return
                if not isinstance(rows, list):
                    raise ExtractionError("评论结构无法识别，请反馈适配问题", False)
                for row in rows:
                    row = obj(row)
                    body = text(obj(row.get("content")).get("message"))
                    key = identifier(row.get("rpid")) or body
                    if not body or key in seen:
                        continue
                    seen.add(key)
                    content.comments.append(
                        CapturedComment(
                            author=text(obj(row.get("member")).get("uname")) or None,
                            content=body,
                            likes=count(row.get("like")),
                            replies=count(row.get("rcount")),
                        )
                    )
                    if len(content.comments) >= self.max_comments:
                        return
                total = obj(data.get("page")).get("count")
                if len(rows) < 20 or (type(total) is int and page * 20 >= total):
                    return
                if time.monotonic() >= deadline:
                    break
            content.capture_warnings.append("热评分页达到请求上限，已保留取得的顶层评论。")
        except ExtractionError as exc:
            content.capture_warnings.append(f"热评未完整取得：{exc}；已有内容已保存。")
