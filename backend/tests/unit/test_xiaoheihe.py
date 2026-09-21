import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.extractors import xiaoheihe
from app.extractors.base import ExtractionError
from app.extractors.generic import PlatformRequests
from app.extractors.heybox_sign import hkey
from app.extractors.registry import ExtractorRegistry
from pydantic import SecretStr
from tests.unit.test_xiaohongshu import transport

FIXTURES = Path(__file__).parents[1] / "fixtures"
HTML = (FIXTURES / "xiaoheihe.html").read_text()
URL = "https://www.xiaoheihe.cn/app/bbs/link/123456"
SHARE = "https://api.xiaoheihe.cn/v3/bbs/app/api/web/share?link_id=opaque123"


def page(number: int) -> dict[str, Any]:
    return json.loads((FIXTURES / f"xiaoheihe-page{number}.json").read_text())


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    calls = []
    monkeypatch.setattr(PlatformRequests, "wait", lambda self: None)

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] in xiaoheihe.PAGE_HOSTS
        assert request.headers["cookie"] == "session=offline"
        if request.url.path == "/v3/bbs/app/api/web/share":
            return httpx.Response(
                302, headers={"location": "https://www.xiaoheihe.cn/app/bbs/link/opaque123"}
            )
        if request.url.path.startswith("/app/bbs/link/"):
            return httpx.Response(
                200, headers={"content-type": "text/html; charset=utf-8"}, text=HTML
            )
        params = request.url.params
        assert params["hkey"] == hkey(xiaoheihe.TREE_PATH, int(params["_time"]), params["nonce"])
        return httpx.Response(200, json=page(int(params["page"])))

    transport(monkeypatch, handle)
    return calls


@pytest.mark.parametrize("url", [URL, SHARE])
def test_heybox_metadata_comments_and_pagination(offline: list[httpx.Request], url: str) -> None:
    content = xiaoheihe.XiaoheiheExtractor(lambda _: SecretStr("session=offline")).extract(url)
    assert content.platform == "xiaoheihe" and content.title == "离线小黑盒笔记"
    assert "保存游戏攻略" in content.text and "secret-script" not in content.text
    assert content.author == "离线盒友" and content.published_at.year == 2024
    assert content.author_url.endswith("/1001")
    assert content.images == [
        "https://images.example.com/heybox.jpg",
        "https://images.example.com/second.jpg",
    ]
    assert len(content.comments) == 12
    assert content.comments[0].likes == 14 and content.comments[0].replies == 2
    assert content.raw_html == HTML
    assert len([r for r in offline if r.url.path == xiaoheihe.TREE_PATH]) == 2


@pytest.mark.parametrize("limit", [0, 2, 8, 10])
def test_comment_limit_is_obeyed(offline: list[httpx.Request], limit: int) -> None:
    content = xiaoheihe.XiaoheiheExtractor(
        lambda _: SecretStr("session=offline"), max_comments=limit
    ).extract(URL)
    assert len(content.comments) == limit and content.comment_capture_limit == limit
    assert len([r for r in offline if r.url.path == xiaoheihe.TREE_PATH]) == (
        1 if limit <= 8 else 2
    )


@pytest.mark.parametrize(
    "url,expected",
    [
        (URL, "xiaoheihe"),
        (SHARE, "xiaoheihe"),
        ("https://www.xiaoheihe.cn.attacker.example/app/bbs/link/1", "web"),
    ],
)
def test_exact_host_matching(url: str, expected: str) -> None:
    assert ExtractorRegistry().get(url).name == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://www.xiaoheihe.cn/home",
        "https://api.xiaoheihe.cn/other?link_id=123",
        SHARE + "&link_id=other",
    ],
)
def test_unsupported_links_fail_before_fetching(url: str) -> None:
    with pytest.raises(ExtractionError, match="帖子链接"):
        xiaoheihe.XiaoheiheExtractor().extract(url)


def test_response_cannot_substitute_another_post(
    monkeypatch: pytest.MonkeyPatch, offline: list[httpx.Request]
) -> None:
    data = page(1)["result"]
    data["link"]["linkid"] = 999
    monkeypatch.setattr(xiaoheihe.HeyboxClient, "page", lambda *args: data)
    with pytest.raises(ExtractionError, match="结构无法识别"):
        xiaoheihe.XiaoheiheExtractor(lambda _: SecretStr("session=offline")).extract(URL)


@pytest.mark.parametrize(
    "status,message",
    [
        ("login", "登录态失效"),
        ("relogin", "登录态失效"),
        ("show_captcha", "验证"),
        ("lack_token", "验证"),
        ("failed", "未返回可用数据"),
    ],
)
def test_api_failure_messages_do_not_leak_platform_body(
    monkeypatch: pytest.MonkeyPatch, status: str, message: str
) -> None:
    transport(
        monkeypatch,
        lambda request: httpx.Response(200, json={"status": status, "msg": "private-upstream"}),
    )
    with pytest.raises(ExtractionError, match=message) as error:
        xiaoheihe.HeyboxClient(None).page("123", 1, 20)
    assert "private" not in str(error.value)


def test_signatures_match_reference_vectors() -> None:
    nonce = "0123456789ABCDEF0123456789ABCDEF"
    assert hkey("/bbs/app/link/tree", 1726833600, nonce) == "2SVXP01"
    assert hkey("/account/restore_login", 1726833600, nonce) == "PWT7Y77"


def test_missing_optional_metadata_is_left_empty() -> None:
    content = xiaoheihe.parse_heybox({"link": {"title": "标题"}}, URL, HTML, 100)
    assert content.author is content.author_url is content.published_at is None
    assert content.text == "" and content.images == []
