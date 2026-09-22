# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.extractors import bilibili
from app.extractors.base import ExtractionError
from app.extractors.generic import PlatformRequests
from app.extractors.registry import ExtractorRegistry
from tests.unit.test_xiaohongshu import transport

FIXTURES = Path(__file__).parents[1] / "fixtures"
URL = "https://www.bilibili.com/video/BV1xx411c7mD"
HTML = (FIXTURES / "bilibili.html").read_text()


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def offline_bili(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    requests = []
    monkeypatch.setattr(PlatformRequests, "wait", lambda self: None)

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "cookie" not in request.headers and "authorization" not in request.headers
        assert request.url.host == "93.184.216.34"
        if request.headers["host"] == "b23.tv":
            return httpx.Response(302, headers={"location": URL})
        path = request.url.path
        if path.startswith("/video/"):
            return httpx.Response(
                200, headers={"content-type": "text/html; charset=utf-8"}, text=HTML
            )
        if path == "/x/player/wbi/v2":
            return httpx.Response(200, json=fixture("bilibili-player.json"))
        if path.startswith("/bfs/subtitle/"):
            assert path.endswith("chinese.json")
            return httpx.Response(200, json=fixture("bilibili-captions.json"))
        if path == "/x/v2/reply":
            assert request.url.params["sort"] == "2"
            return httpx.Response(
                200, json=fixture(f"bilibili-comments{request.url.params['pn']}.json")
            )
        raise AssertionError(path)

    transport(monkeypatch, handle)
    return requests


@pytest.mark.parametrize("url", [URL, "https://b23.tv/offline", URL + "?p=2"])
def test_video_metadata_captions_and_hot_comment_pages(
    offline_bili: list[httpx.Request], url: str
) -> None:
    c = bilibili.BilibiliExtractor().extract(url)
    assert c.title == "离线视频笔记" and c.author == "离线作者"
    assert "视频简介" in c.text and "字幕（中文）" in c.text and "结合字幕与热评" in c.text
    assert c.author_url == "https://space.bilibili.com/42" and c.published_at.year == 2024
    assert len(c.images) == 1 and len(c.comments) == 23
    assert c.comments[0].likes == 99 and c.comments[0].replies == 2
    assert c.raw_html == HTML and c.capture_warnings == []
    player = next(r for r in offline_bili if r.url.path == "/x/player/wbi/v2")
    assert player.url.params["cid"] == ("200" if url.endswith("p=2") else "100")


@pytest.mark.parametrize("limit", [0, 1, 20, 21])
def test_limits_skip_comment_requests_when_disabled(
    offline_bili: list[httpx.Request], limit: int
) -> None:
    c = bilibili.BilibiliExtractor(max_comments=limit).extract(URL)
    assert len(c.comments) == limit
    assert sum(r.url.path == "/x/v2/reply" for r in offline_bili) == (
        0 if limit == 0 else 1 if limit <= 20 else 2
    )
    assert "字幕" in c.text


@pytest.mark.parametrize("suffix", ["?p=0", "?p=-1", "?p=abc", "?p=1&p=2", "/other"])
def test_invalid_video_url_fails_before_network(suffix: str) -> None:
    with pytest.raises(ExtractionError):
        bilibili.BilibiliExtractor().extract(URL + suffix)


def test_wrong_video_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bilibili,
        "fetch_html",
        lambda url, **kwargs: (HTML.replace("BV1xx411c7mD", "BV1yy411c7mD"), url),
    )
    with pytest.raises(ExtractionError, match="链接不符"):
        bilibili.BilibiliExtractor().extract(URL)


@pytest.mark.parametrize(
    "code,word", [(-101, "登录"), (-352, "验证"), (-412, "验证"), (-404, "不存在")]
)
def test_optional_restrictions_preserve_metadata_without_upstream_text(
    monkeypatch: pytest.MonkeyPatch, code: int, word: str
) -> None:
    monkeypatch.setattr(bilibili, "fetch_html", lambda url, **kwargs: (HTML, url))
    monkeypatch.setattr(
        bilibili,
        "fetch_json",
        lambda *args, **kwargs: {"code": code, "message": "private-upstream"},
    )
    c = bilibili.BilibiliExtractor().extract(URL)
    assert c.title and "视频简介" in c.text and c.comments == []
    assert word in str(c.capture_warnings) and "private" not in str(c.capture_warnings)


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example/sub.json",
        "http://aisubtitle.hdslb.com/sub.json",
        "https://127.0.0.1/sub.json",
    ],
)
def test_subtitle_host_restrictions(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setattr(bilibili, "fetch_html", lambda url, **kwargs: (HTML, url))
    data = fixture("bilibili-player.json")["data"]
    data["subtitle"]["subtitles"] = [{"subtitle_url": url}]
    monkeypatch.setattr(bilibili.BilibiliExtractor, "api", lambda *args: data)
    monkeypatch.setattr(
        bilibili,
        "fetch_json",
        lambda *args, **kwargs: pytest.fail("must not fetch untrusted subtitle host"),
    )
    c = bilibili.BilibiliExtractor(max_comments=0).extract(URL)
    assert c.title and "未取得字幕" in c.capture_warnings[0]


def test_no_public_subtitles_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bilibili, "fetch_html", lambda url, **kwargs: (HTML, url))
    monkeypatch.setattr(
        bilibili.BilibiliExtractor, "api", lambda *args: {"need_login_subtitle": True}
    )
    c = bilibili.BilibiliExtractor(max_comments=0).extract(URL)
    assert c.capture_warnings == ["字幕需要登录，已保存视频简介。"]


def test_exact_platform_matching() -> None:
    assert ExtractorRegistry().get(URL).name == "bilibili"
    assert (
        ExtractorRegistry().get("https://www.bilibili.com.attacker.example/video/BV1xx411c7mD").name
        == "web"
    )
