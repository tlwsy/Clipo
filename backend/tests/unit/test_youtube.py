# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.extractors import youtube
from app.extractors.base import ExtractionError
from app.extractors.generic import PlatformRequests
from app.extractors.registry import ExtractorRegistry
from tests.unit.test_xiaohongshu import transport

FIXTURES = Path(__file__).parents[1] / "fixtures"
HTML = (FIXTURES / "youtube.html").read_text()
URL = "https://www.youtube.com/watch?v=abcDEF123_-"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def offline_youtube(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    calls = []
    monkeypatch.setattr(PlatformRequests, "wait", lambda self: None)

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "www.youtube.com"
        assert "cookie" not in request.headers and "authorization" not in request.headers
        if request.url.path == "/watch":
            assert request.method == "GET" and request.url.params["v"] == "abcDEF123_-"
            return httpx.Response(
                200, headers={"content-type": "text/html; charset=utf-8"}, text=HTML
            )
        if request.url.path == "/api/timedtext":
            assert request.url.params["fmt"] == "json3"
            return httpx.Response(200, json=fixture("youtube-captions.json"))
        assert request.url.path == "/youtubei/v1/next" and request.method == "POST"
        body = json.loads(request.content)
        assert body["context"]["client"]["clientName"] == "WEB"
        token = body["continuation"]
        assert token in ("initial", "top", "page2")
        return httpx.Response(200, json=fixture(f"youtube-comments-{token}.json"))

    transport(monkeypatch, handle)
    return calls


@pytest.mark.parametrize(
    "url",
    [
        URL,
        "https://youtu.be/abcDEF123_-",
        "https://m.youtube.com/shorts/abcDEF123_-",
        "https://www.youtube.com/live/abcDEF123_-",
    ],
)
def test_metadata_captions_hot_sort_both_comment_schemas(
    offline_youtube: list[httpx.Request], url: str
) -> None:
    c = youtube.YoutubeExtractor().extract(url)
    assert c.platform == "youtube" and c.title == "离线 YouTube 视频" and c.author == "离线创作者"
    assert c.author_url.endswith("a" * 22) and c.published_at.year == 2024
    assert (
        "视频简介" in c.text
        and "字幕（en，自动字幕）" in c.text
        and "First save the source." in c.text
    )
    assert len(c.images) == 1 and len(c.comments) == 3
    assert c.comments[0].content == "A useful comment 1 with practical details."
    assert c.comments[0].likes == 1234 and c.comments[0].replies == 2
    assert (
        c.comments[2].likes == 42
        and c.comments[2].replies == 3
        and c.comments[2].author == "Viewer 3"
    )
    assert c.capture_warnings == [] and c.raw_html == HTML
    assert len(offline_youtube) == 5


@pytest.mark.parametrize("limit", [0, 1, 2, 3])
def test_comment_limits_and_disable(offline_youtube: list[httpx.Request], limit: int) -> None:
    c = youtube.YoutubeExtractor(max_comments=limit).extract(URL)
    assert len(c.comments) == limit and c.comment_capture_limit == limit
    assert sum(r.method == "POST" for r in offline_youtube) == (
        0 if limit == 0 else 2 if limit <= 2 else 3
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/playlist?list=abc",
        "https://www.youtube.com/watch?v=abcDEF123_-&v=abcdefghijk",
        "https://youtu.be/short",
        "https://www.youtube.com/@channel",
    ],
)
def test_unsupported_urls_fail_before_fetch(url: str) -> None:
    with pytest.raises(ExtractionError):
        youtube.YoutubeExtractor().extract(url)


@pytest.mark.parametrize("status", ["LOGIN_REQUIRED", "AGE_CHECK_REQUIRED", "UNPLAYABLE"])
def test_restricted_player_is_not_saved_as_a_video(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    monkeypatch.setattr(
        youtube,
        "fetch_html",
        lambda url, **kwargs: (HTML.replace('"status": "OK"', f'"status": "{status}"'), url),
    )
    with pytest.raises(ExtractionError, match="YouTube"):
        youtube.YoutubeExtractor().extract(URL)


def test_player_must_match_requested_video(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        youtube,
        "fetch_html",
        lambda url, **kwargs: (
            HTML.replace('"videoId": "abcDEF123_-"', '"videoId": "different00"'),
            url,
        ),
    )
    with pytest.raises(ExtractionError, match="结构"):
        youtube.YoutubeExtractor().extract(URL)


@pytest.mark.parametrize(
    "caption_url",
    [
        "https://attacker.example/api/timedtext?v=abcDEF123_-",
        "http://www.youtube.com/api/timedtext?v=abcDEF123_-",
        "https://127.0.0.1/api/timedtext?v=abcDEF123_-",
        "https://www.youtube.com/api/timedtext?v=other000000",
    ],
)
def test_subtitle_links_restricted_to_video_and_official_https(
    monkeypatch: pytest.MonkeyPatch, caption_url: str
) -> None:
    html = HTML.replace("https://www.youtube.com/api/timedtext?v=abcDEF123_-&lang=en", caption_url)
    monkeypatch.setattr(youtube, "fetch_html", lambda url, **kwargs: (html, url))
    monkeypatch.setattr(
        youtube, "fetch_json", lambda *args, **kwargs: pytest.fail("untrusted caption request")
    )
    c = youtube.YoutubeExtractor(max_comments=0).extract(URL)
    assert c.title and "未取得 YouTube 字幕" in c.capture_warnings[0]


def test_missing_captions_comments_and_abbreviated_counts_stay_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = HTML.replace('"captionTracks"', '"noTracks"').replace(
        "comment-item-section", "unrelated"
    )
    monkeypatch.setattr(youtube, "fetch_html", lambda url, **kwargs: (html, url))
    c = youtube.YoutubeExtractor().extract(URL)
    assert len(c.capture_warnings) == 2 and c.comments == []
    assert youtube.exact_count("1.2K") == 0 and youtube.exact_count("1,234 likes") == 1234


def test_comment_loop_is_bounded_and_partial_results_kept(
    monkeypatch: pytest.MonkeyPatch, offline_youtube: list[httpx.Request]
) -> None:
    calls = []

    def next_page(self: object, token: str, config: dict, requests: object) -> dict:
        calls.append(token)
        return fixture("youtube-comments-top.json")

    monkeypatch.setattr(youtube.YoutubeExtractor, "next_page", next_page)
    c = youtube.YoutubeExtractor().extract(URL)
    assert len(c.comments) == 2 and len(calls) == 2 and "提前结束" in c.capture_warnings[-1]


@pytest.mark.parametrize("status", [302, 403, 429])
def test_post_api_redirects_and_errors_preserve_original_without_leaking(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/watch":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=HTML.replace('"captionTracks"', '"noTracks"'),
            )
        return httpx.Response(
            status, headers={"location": "https://attacker.example/leak"}, text="private-upstream"
        )

    monkeypatch.setattr(PlatformRequests, "wait", lambda self: None)
    transport(monkeypatch, handle)
    c = youtube.YoutubeExtractor().extract(URL)
    assert c.title and "视频简介" in c.text and len(calls) == 2
    assert "热评未完整取得" in c.capture_warnings[-1] and "private" not in str(c.capture_warnings)


def test_exact_host_matching_and_nonexecuting_config() -> None:
    assert ExtractorRegistry().get(URL).name == "youtube"
    assert (
        ExtractorRegistry().get("https://www.youtube.com.attacker.example/watch?v=abcDEF123_-").name
        == "web"
    )
    assert youtube.config_object("<script>ytcfg.set(evil())</script>") == {}
    assert youtube.config_object(HTML)["INNERTUBE_CONTEXT"]["client"]["clientName"] == "WEB"


def test_changed_comment_schema_is_reported_without_discarding_prior_comments(
    monkeypatch: pytest.MonkeyPatch, offline_youtube: list[httpx.Request]
) -> None:
    original = youtube.YoutubeExtractor.next_page

    def page(self: youtube.YoutubeExtractor, token: str, config: dict, requests: object) -> dict:
        response = original(self, token, config, requests)
        if token == "page2":
            response.pop("frameworkUpdates")
        return response

    monkeypatch.setattr(youtube.YoutubeExtractor, "next_page", page)
    content = youtube.YoutubeExtractor().extract(URL)
    assert len(content.comments) == 2 and content.title
    assert "评论结构无法识别" in content.capture_warnings[-1]
