import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura
from lxml import html as lxml_html
from pydantic import SecretStr
from readability import Document

from app.extractors.base import CapturedContent, ExtractionError
from app.security.urls import normalize_url, public_addresses

MAX_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class ScopedCookie:
    value: SecretStr
    hosts: frozenset[str]

    def headers(self, url: str) -> dict[str, str]:
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.port in (None, 443) and parts.hostname in self.hosts:
            return {"Cookie": self.value.get_secret_value()}
        return {}


def _fetch(
    url: str,
    *,
    cookie: ScopedCookie | None = None,
    allowed_hosts: frozenset[str] | None = None,
    check_status: Callable[[int], None] | None = None,
    headers: dict[str, str] | None = None,
    json_response: bool = False,
    before_request: Callable[[], None] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Validate every hop, pin DNS results, preserve TLS SNI and never use ambient proxies."""
    current = normalize_url(url)
    started = time.monotonic()
    try:
        with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
            for _ in range(6):
                if time.monotonic() - started > 60:
                    raise ExtractionError("网页读取超时，请稍后重试")
                parts = urlsplit(current)
                if allowed_hosts is not None and parts.hostname not in allowed_hosts:
                    raise ExtractionError("平台链接跳转到不支持的网站，请使用原始帖子链接", False)
                if before_request is not None:
                    before_request()
                address = public_addresses(current)[0]
                pinned = httpx.URL(current).copy_with(host=address)
                # Pinned URLs can share an IP. Never replay server cookies across hosts/hops.
                client.cookies.clear()
                with client.stream(
                    "POST" if json_body is not None else "GET",
                    pinned,
                    **({"json": json_body} if json_body is not None else {}),
                    headers={
                        "Host": parts.netloc,
                        "User-Agent": (headers or {}).get(
                            "User-Agent", "Clipo/0.1 (+self-hosted reader)"
                        ),
                        "Accept": (
                            "application/json"
                            if json_response
                            else "text/html,application/xhtml+xml"
                        ),
                        **(headers if current == normalize_url(url) and headers else {}),
                        **(cookie.headers(current) if cookie else {}),
                    },
                    extensions={"sni_hostname": parts.hostname},
                ) as response:
                    if response.is_redirect:
                        if json_response:
                            raise ExtractionError(
                                "平台接口发生跳转，请更新 Cookie 或稍后重试", False
                            )
                        location = response.headers.get("location")
                        if not location:
                            raise ExtractionError("网页重定向缺少地址，请检查原始链接", False)
                        current = normalize_url(urljoin(current, location))
                        continue
                    if check_status is not None:
                        check_status(response.status_code)
                    if response.status_code in (401, 403):
                        raise ExtractionError(
                            "网页限制访问或需要登录，请尝试公开网页；平台登录支持将在后续版本提供",
                            False,
                        )
                    if response.status_code >= 400:
                        raise ExtractionError(
                            "网页请求失败，请检查链接是否有效，或稍后重试",
                            response.status_code == 429 or response.status_code >= 500,
                        )
                    mime = response.headers.get("content-type", "").split(";")[0].lower()
                    expected = (
                        ("application/json",)
                        if json_response
                        else ("text/html", "application/xhtml+xml")
                    )
                    if mime not in expected:
                        raise ExtractionError(
                            (
                                "平台接口未返回 JSON，请检查登录状态或稍后重试"
                                if json_response
                                else "该链接不是 HTML 网页，请分享文章页面链接"
                            ),
                            False,
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise ExtractionError("网页超过 5 MB，请尝试更精简的文章链接", False)
                        if time.monotonic() - started > 60:
                            raise ExtractionError("网页读取超时，请稍后重试")
                    # Honor HTTP charset, otherwise let the HTML parser detect meta charset.
                    if json_response:
                        content = body.decode("utf-8-sig", errors="strict")
                    elif "charset=" in response.headers.get("content-type", "").lower():
                        content = body.decode(response.encoding or "utf-8", errors="replace")
                    else:
                        content = trafilatura.utils.decode_file(bytes(body))
                    return content, current
    except httpx.HTTPError as exc:
        raise ExtractionError("无法连接网页，请检查链接或稍后重试") from exc
    raise ExtractionError("网页重定向次数过多，请使用最终文章链接", False)


class PlatformRequests:
    """Keep one UA per capture and space its requests, without sharing credentials."""

    USER_AGENTS = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    )

    def __init__(self) -> None:
        self.user_agent = random.choice(self.USER_AGENTS)
        self.last_request: float | None = None

    def wait(self) -> None:
        if self.last_request is not None:
            delay = self.last_request + random.uniform(1, 1.5) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        self.last_request = time.monotonic()


def fetch_html(
    url: str,
    *,
    cookie: ScopedCookie | None = None,
    allowed_hosts: frozenset[str] | None = None,
    check_status: Callable[[int], None] | None = None,
    requests: PlatformRequests | None = None,
) -> tuple[str, str]:
    return _fetch(
        url,
        cookie=cookie,
        allowed_hosts=allowed_hosts,
        check_status=check_status,
        headers={"User-Agent": requests.user_agent} if requests else None,
        before_request=requests.wait if requests else None,
    )


def fetch_json(
    url: str,
    *,
    allowed_hosts: frozenset[str],
    cookie: ScopedCookie | None = None,
    headers: dict[str, str] | None = None,
    check_status: Callable[[int], None] | None = None,
    requests: PlatformRequests | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        body, _ = _fetch(
            url,
            cookie=cookie,
            allowed_hosts=allowed_hosts,
            check_status=check_status,
            headers={
                **(headers or {}),
                **({"User-Agent": requests.user_agent} if requests else {}),
            },
            json_response=True,
            json_body=json_body,
            before_request=requests.wait if requests else None,
        )
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, RecursionError):
        raise ExtractionError("平台接口数据格式已变化，请稍后重试或反馈适配问题", False) from None


def parse_html(html: str, url: str) -> CapturedContent:
    if not html.strip():
        raise ExtractionError("网页没有返回内容，请检查链接后重试", False)
    doc = trafilatura.bare_extraction(
        html, url=url, with_metadata=True, include_comments=False, include_tables=True
    )
    tree = lxml_html.fromstring(html)
    text = doc.text if doc else None
    if not text or len(text.strip()) < 40:
        readable = Document(html)
        body = lxml_html.fromstring(readable.summary())
        for node in body.xpath("//script|//style|//nav|//footer|//form"):
            node.drop_tree()
        text = "\n".join(part.strip() for part in body.itertext() if part.strip())
    if not text or len(text.strip()) < 20:
        raise ExtractionError(
            "未找到可保存的正文；页面可能需要登录或 JavaScript，请尝试文章原始链接", False
        )
    titles = tree.xpath('//meta[@property="og:title"]/@content|//title/text()')
    title = (doc.title if doc else None) or (titles[0] if titles else urlsplit(url).hostname)
    authors = tree.xpath('//meta[@name="author"]/@content')
    author = (doc.author if doc else None) or (authors[0].strip() if authors else None)
    images = []
    for value in tree.xpath('//meta[@property="og:image"]/@content|//article//img/@src')[:50]:
        image_url = urljoin(url, value)
        if urlsplit(image_url).scheme in ("https", "http") and image_url not in images:
            images.append(image_url)
    published_at = None
    if doc and doc.date:
        try:
            published_at = datetime.fromisoformat(doc.date).replace(tzinfo=UTC)
        except ValueError:
            pass
    return CapturedContent(
        url=url,
        title=str(title)[:1000],
        text=text.strip(),
        author=author,
        published_at=published_at,
        images=images,
        raw_html=html,
    )


class GenericExtractor:
    name = "web"

    def matches(self, url: str) -> bool:
        return urlsplit(url).scheme in ("http", "https")

    def extract(self, url: str, payload: dict | None = None) -> CapturedContent:
        html, final_url = fetch_html(url)
        return parse_html(html, final_url)
