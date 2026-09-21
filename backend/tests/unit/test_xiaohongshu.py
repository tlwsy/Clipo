import json
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.extractors import generic
from app.extractors.base import ExtractionError
from app.extractors.generic import ScopedCookie
from app.extractors.registry import ExtractorRegistry
from app.extractors.xiaohongshu import (
    COOKIE_HOSTS,
    XiaohongshuExtractor,
    parse_xiaohongshu,
)
from app.security.urls import UnsafeURL
from pydantic import SecretStr

FIXTURES = Path(__file__).parents[1] / "fixtures"
HTML = (FIXTURES / "xiaohongshu.html").read_text()
URL = "https://www.xiaohongshu.com/explore/64abc123?xsec_token=offline"


def state_html(note: dict[str, Any], comments: Any = None) -> str:
    state = {"note": {"noteDetailMap": {"64abc123": {"note": note, "comments": comments}}}}
    return f"<script>window.__INITIAL_STATE__={json.dumps(state)}</script>"


def transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    original = httpx.Client
    monkeypatch.setattr(
        generic.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: [(0, 0, 0, "", ("93.184.216.34", 443))]
    )


def test_extracts_requested_note_metadata_and_embedded_comments() -> None:
    content = parse_xiaohongshu(HTML, URL)
    assert content.platform == "xiaohongshu"
    assert content.url == URL
    assert content.title == "离线采集笔记"
    assert (
        content.text
        == '保留正文与来源，方便日后回顾。\n字符串 undefined 和 "undefined" 必须原样保存。'
    )
    assert content.author == "离线作者"
    assert content.author_url == "https://www.xiaohongshu.com/user/profile/author123"
    assert content.published_at == datetime.fromtimestamp(1726833600, tz=UTC)
    assert content.images == [
        "https://images.example.com/xhs-cover.jpg",
        "https://images.example.com/xhs-detail.jpg",
    ]
    assert len(content.comments) == 10
    assert content.comments[0].author == "读者一"
    assert content.comments[0].likes == 12 and content.comments[0].replies == 2
    assert content.comments[1].author == "读者二"
    assert content.comments[1].likes == 9 and content.comments[1].replies == 1
    assert content.comments[3].author is None
    assert content.raw_html == HTML


@pytest.mark.parametrize("path", ["explore/64abc123", "discovery/item/64abc123/"])
def test_supported_note_paths_and_missing_fields(path: str) -> None:
    content = parse_xiaohongshu(
        state_html({"desc": "仅有正文"}), "https://www.xiaohongshu.com/" + path
    )
    assert content.title == "" and content.text == "仅有正文"
    assert content.author is content.author_url is content.published_at is None
    assert content.images == content.comments == []


@pytest.mark.parametrize(
    "url,expected",
    [
        (URL, "xiaohongshu"),
        ("https://xiaohongshu.com/discovery/item/64abc123", "xiaohongshu"),
        ("https://xhslink.com/a/offline", "xiaohongshu"),
        ("https://www.xhslink.com/a/offline", "xiaohongshu"),
        ("https://xhslink.cn/o/offline", "xiaohongshu"),
        ("https://www.xhslink.cn/o/offline", "xiaohongshu"),
        ("https://www.xiaohongshu.com.attacker.example/explore/64abc123", "web"),
        ("https://fake-xiaohongshu.com/explore/64abc123", "web"),
        ("https://example.com/?url=https://www.xiaohongshu.com", "web"),
    ],
)
def test_registry_matches_exact_platform_hosts(url: str, expected: str) -> None:
    assert ExtractorRegistry().get(url).name == expected


@pytest.mark.parametrize("time", [None, "昨天", -1, True, 10**30, float("nan")])
def test_bad_optional_fields_are_left_empty(time: Any) -> None:
    content = parse_xiaohongshu(
        state_html(
            {"desc": "正文", "time": time, "user": [], "imageList": "bad"},
            {"list": [None, {"content": "补充信息", "likeCount": "1万+", "subCommentCount": -2}]},
        ),
        URL,
    )
    assert content.published_at is content.author is content.author_url is None
    assert content.images == []
    assert content.comments[0].likes == content.comments[0].replies == 0


def test_embedded_comments_are_bounded_and_image_only_notes_are_supported() -> None:
    content = parse_xiaohongshu(
        state_html(
            {"imageList": [{"urlPre": "https://images.example.com/photo.jpg"}]},
            {"list": [{"content": f"评论 {index}"} for index in range(150)]},
        ),
        URL,
    )
    assert content.title == content.text == ""
    assert len(content.images) == 1 and len(content.comments) == 100


@pytest.mark.parametrize("limit,expected", [(0, []), (1, [1]), (2, [1, 10]), (100, [1, 10, 30])])
def test_comment_limit_counts_valid_unique_rows_in_page_order(
    limit: int, expected: list[int]
) -> None:
    html = (FIXTURES / "xiaohongshu-comment-limit.html").read_text()
    content = parse_xiaohongshu(html, URL, max_comments=limit)
    assert [comment.likes for comment in content.comments] == expected
    assert content.comment_capture_limit == limit
    assert content.text == "正文应完整保留。"
    assert content.raw_html == html


@pytest.mark.parametrize("limit", [-1, 101, True, 2.5])
def test_parser_rejects_invalid_comment_limits(limit: Any) -> None:
    with pytest.raises(ValueError):
        parse_xiaohongshu(HTML, URL, max_comments=limit)


@pytest.mark.parametrize(
    "html,url,message,retryable",
    [
        ((FIXTURES / "xiaohongshu-login.html").read_text(), URL, "登录态失效", False),
        ((FIXTURES / "xiaohongshu-changed.html").read_text(), URL, "结构可能已变化", False),
        (HTML, "https://www.xiaohongshu.com/login", "登录态失效", False),
        (HTML, "https://www.xiaohongshu.com/user/profile/author123", "帖子链接", False),
        (HTML, "https://xhslink.com/unresolved", "短链接未跳转", False),
        (HTML, URL.replace("64abc123", "missing"), "结构可能已变化", False),
        (state_html({"noteId": "other", "desc": "错误帖子"}), URL, "结构可能已变化", False),
        (
            '<script>window.__INITIAL_STATE__={"note":alert("secret")}</script>',
            URL,
            "结构可能已变化",
            False,
        ),
        ("<title>小红书 - 安全验证</title>", URL, "安全验证", False),
        ("<title>小红书 - 访问频繁</title>", URL, "过于频繁", True),
        ("", URL, "结构可能已变化", False),
    ],
)
def test_page_errors_are_actionable_without_generic_fallback(
    html: str, url: str, message: str, retryable: bool
) -> None:
    with pytest.raises(ExtractionError) as error:
        parse_xiaohongshu(html, url)
    assert message in str(error.value)
    assert error.value.retryable is retryable
    assert "secret" not in str(error.value)


def test_shortlink_sends_cookie_only_to_https_platform_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.extractors.xiaohongshu.XhsClient.comments",
        lambda *args: {"comments": [], "has_more": False},
    )
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "93.184.216.34"
        if len(requests) == 1:
            assert request.headers["host"] == "xhslink.com"
            assert "cookie" not in request.headers
            return httpx.Response(
                302, headers={"location": URL, "set-cookie": "injected=bad; Path=/"}
            )
        assert request.headers["host"] == "www.xiaohongshu.com"
        assert request.extensions["sni_hostname"] == "www.xiaohongshu.com"
        assert request.url.params["xsec_token"] == "offline"
        assert request.headers["cookie"] == "web_session=private"
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=HTML)

    transport(monkeypatch, handle)
    extractor = XiaohongshuExtractor(lambda platform: SecretStr("web_session=private"))
    assert extractor.extract("https://xhslink.com/a/offline").title == "离线采集笔记"
    assert len(requests) == 2


@pytest.mark.parametrize(
    "redirect",
    [
        "http://www.xiaohongshu.com/explore/64abc123",
        "https://www.xiaohongshu.com:80/explore/64abc123",
        "https://example.com/steal",
        "https://xhslink.com/steal",
        "https://www.xiaohongshu.com.attacker.example/steal",
    ],
)
def test_scoped_cookie_and_server_cookies_never_leak_on_redirect(
    monkeypatch: pytest.MonkeyPatch, redirect: str
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            assert request.headers["cookie"] == "web_session=private"
            return httpx.Response(
                302, headers={"location": redirect, "set-cookie": "leak=private; Path=/"}
            )
        assert "cookie" not in request.headers
        return httpx.Response(200, headers={"content-type": "text/html"}, text=HTML)

    transport(monkeypatch, handle)
    cookie = ScopedCookie(SecretStr("web_session=private"), COOKIE_HOSTS)
    generic.fetch_html(URL, cookie=cookie)
    assert len(requests) == 2
    assert "private" not in repr(cookie)


@pytest.mark.parametrize("redirect", ["https://attacker.example/steal", "http://127.0.0.1/private"])
def test_platform_redirect_rejected_before_contacting_other_host(
    monkeypatch: pytest.MonkeyPatch, redirect: str
) -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"location": redirect})

    transport(monkeypatch, handle)
    with pytest.raises(ExtractionError):
        XiaohongshuExtractor(lambda _: SecretStr("web_session=private")).extract(URL)
    assert len(calls) == 1


def test_platform_rejects_mixed_private_dns_before_sending_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail("Unsafe address must not receive any request")

    transport(monkeypatch, unexpected)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (0, 0, 0, "", ("93.184.216.34", 443)),
            (0, 0, 0, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(UnsafeURL):
        XiaohongshuExtractor(lambda _: SecretStr("web_session=private")).extract(URL)


@pytest.mark.parametrize(
    "status,message,retryable",
    [
        (401, "登录态失效", False),
        (403, "限制访问", False),
        (461, "限制访问", False),
        (471, "限制访问", False),
        (429, "过于频繁", True),
        (404, "不存在或已删除", False),
        (503, "稍后重试", True),
    ],
)
def test_http_diagnostics(
    monkeypatch: pytest.MonkeyPatch, status: int, message: str, retryable: bool
) -> None:
    transport(monkeypatch, lambda _: httpx.Response(status, text="upstream-private-response"))
    with pytest.raises(ExtractionError) as error:
        XiaohongshuExtractor().extract(URL)
    assert message in str(error.value) and error.value.retryable is retryable
    assert "private" not in str(error.value)


def test_empty_js_collections_are_data_only_and_strings_stay_intact() -> None:
    html = (FIXTURES / "xiaohongshu-collections.html").read_text()
    content = parse_xiaohongshu(html, URL)
    assert content.title == "集合语法兼容"
    assert content.text == "new Map([])、new Set([])、undefined 字符串不应被修改。"
    assert content.comments == []


@pytest.mark.parametrize(
    "expression", ["new Map(evil())", "new Map([[evil(), 1]])", "eval('secret')"]
)
def test_unknown_js_expressions_remain_rejected(expression: str) -> None:
    html = (
        (FIXTURES / "xiaohongshu-collections.html")
        .read_text()
        .replace("new Map([])", expression, 1)
    )
    with pytest.raises(ExtractionError, match="页面结构"):
        parse_xiaohongshu(html, URL)
