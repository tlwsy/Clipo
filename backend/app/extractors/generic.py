import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura
from lxml import html as lxml_html
from readability import Document

from app.extractors.base import CapturedContent, ExtractionError
from app.security.urls import normalize_url, public_addresses

MAX_BYTES = 5 * 1024 * 1024


def fetch_html(url: str) -> tuple[str, str]:
    """Validate every hop, pin DNS results, preserve TLS SNI and never use ambient proxies."""
    current = normalize_url(url)
    started = time.monotonic()
    try:
        with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
            for _ in range(6):
                address = public_addresses(current)[0]
                parts = urlsplit(current)
                pinned = httpx.URL(current).copy_with(host=address)
                with client.stream(
                    "GET",
                    pinned,
                    headers={
                        "Host": parts.netloc,
                        "User-Agent": "Clipo/0.1 (+self-hosted reader)",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                    extensions={"sni_hostname": parts.hostname},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ExtractionError("网页重定向缺少地址，请检查原始链接", False)
                        current = normalize_url(urljoin(current, location))
                        continue
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
                    if mime not in ("text/html", "application/xhtml+xml"):
                        raise ExtractionError("该链接不是 HTML 网页，请分享文章页面链接", False)
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise ExtractionError("网页超过 5 MB，请尝试更精简的文章链接", False)
                        if time.monotonic() - started > 60:
                            raise ExtractionError("网页读取超时，请稍后重试")
                    # Honor HTTP charset, otherwise let the HTML parser detect meta charset.
                    if "charset=" in response.headers.get("content-type", "").lower():
                        content = body.decode(response.encoding or "utf-8", errors="replace")
                    else:
                        content = trafilatura.utils.decode_file(bytes(body))
                    return content, current
    except httpx.HTTPError as exc:
        raise ExtractionError("无法连接网页，请检查链接或稍后重试") from exc
    raise ExtractionError("网页重定向次数过多，请使用最终文章链接", False)


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
