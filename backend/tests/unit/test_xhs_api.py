import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from app.extractors import generic, xiaohongshu
from app.extractors.base import ExtractionError
from app.extractors.generic import PlatformRequests, ScopedCookie, fetch_json
from app.extractors.xhs_api import API_HOSTS, XhsClient
from pydantic import SecretStr
from tests.unit.test_xiaohongshu import HTML, URL, transport

FIXTURES = Path(__file__).parents[1] / "fixtures"
COOKIE = SecretStr("a1=offline-device; web_session=offline-session; webId=offline-web")


@pytest.fixture
def requests(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    calls: list[httpx.Request] = []
    monkeypatch.setattr(PlatformRequests, "wait", lambda self: None)
    monkeypatch.setattr(xiaohongshu, "fetch_html", lambda url, **kwargs: (HTML, url))

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "edith.xiaohongshu.com"
        assert request.extensions["sni_hostname"] == "edith.xiaohongshu.com"
        assert request.headers["cookie"] == COOKIE.get_secret_value()
        assert request.headers["x-s"].startswith("XYS_")
        assert request.headers["x-t"].isdigit()
        assert request.headers["x-s-common"]
        cursor = request.url.params["cursor"]
        fixture = (
            "xiaohongshu-comments-page2.json"
            if cursor == "page2"
            else "xiaohongshu-comments-page1.json"
        )
        return httpx.Response(200, json=json.loads((FIXTURES / fixture).read_text()))

    transport(monkeypatch, handle)
    return calls


def test_signed_pagination_keeps_html_comments_and_merges_unique_api_rows(
    requests: list[httpx.Request],
) -> None:
    content = xiaohongshu.XiaohongshuExtractor(lambda _: COOKIE).extract(URL)
    assert len(content.comments) == 12
    assert content.comments[10].author == "分页读者"
    assert content.comments[10].likes == 15 and content.comments[10].replies == 2
    assert content.capture_warnings == [] and content.raw_html == HTML
    assert [request.url.params["cursor"] for request in requests] == ["offline-cursor", "page2"]
    assert all(request.url.params["note_id"] == "64abc123" for request in requests)
    assert len({request.headers["user-agent"] for request in requests}) == 1


@pytest.mark.parametrize("limit,expected_requests", [(0, 0), (5, 0), (10, 0), (11, 1)])
def test_pagination_stops_at_capture_limit(
    requests: list[httpx.Request], limit: int, expected_requests: int
) -> None:
    content = xiaohongshu.XiaohongshuExtractor(lambda _: COOKIE, max_comments=limit).extract(URL)
    assert len(content.comments) == limit
    assert len(requests) == expected_requests


@pytest.mark.parametrize("cookie,token", [(None, "offline"), (COOKIE, "")])
def test_missing_pagination_prerequisites_preserve_content_with_a_notice(
    requests: list[httpx.Request], cookie: SecretStr | None, token: str
) -> None:
    content = xiaohongshu.XiaohongshuExtractor(lambda _: cookie).extract(
        URL.replace("offline", token)
    )
    assert content.text and len(content.comments) == 10
    assert "仅保存页面已有评论" in content.capture_warnings[0]
    assert requests == []


def test_cursor_cycle_is_bounded_and_reported(
    monkeypatch: pytest.MonkeyPatch, requests: list[httpx.Request]
) -> None:
    monkeypatch.setattr(
        XhsClient,
        "comments",
        lambda *args: {"comments": [], "cursor": "offline-cursor", "has_more": True},
    )
    content = xiaohongshu.XiaohongshuExtractor(lambda _: COOKIE).extract(URL)
    assert len(content.comments) == 10 and "提前结束" in content.capture_warnings[0]


@pytest.mark.parametrize(
    "status,message", [(401, "登录态失效"), (403, "限制访问"), (406, "限制访问"), (429, "过于频繁")]
)
def test_json_errors_are_classified_without_upstream_disclosure(
    monkeypatch: pytest.MonkeyPatch, status: int, message: str
) -> None:
    transport(monkeypatch, lambda request: httpx.Response(status, text="private-upstream-body"))
    with pytest.raises(ExtractionError, match=message) as error:
        XhsClient(COOKIE).comments("64abc123", "offline", "")
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "data,expected",
    [({"result": {"success": True}}, True), ({"result": {"success": False}}, False)],
)
def test_login_probe_requires_explicit_platform_login_result(
    monkeypatch: pytest.MonkeyPatch, data: dict[str, Any], expected: bool
) -> None:
    transport(
        monkeypatch, lambda request: httpx.Response(200, json={"success": True, "data": data})
    )
    assert XhsClient(COOKIE).check_login() is expected


def test_unknown_login_result_is_not_treated_as_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    transport(monkeypatch, lambda request: httpx.Response(200, json={"success": True, "data": {}}))
    with pytest.raises(ExtractionError, match="未返回明确"):
        XhsClient(COOKIE).check_login()


@pytest.mark.parametrize("value", ["token&extra=private", "token#private", "token\nprivate"])
def test_signer_rejects_query_injection_before_network(value: str) -> None:
    with pytest.raises(ExtractionError, match="分页参数"):
        XhsClient(COOKIE).comments("64abc123", value, "")


def test_json_redirect_does_not_forward_cookie_or_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            302, headers={"location": "https://attacker.example/", "set-cookie": "private=secret"}
        )

    transport(monkeypatch, handle)
    with pytest.raises(ExtractionError, match="跳转"):
        fetch_json(
            "https://edith.xiaohongshu.com/api",
            allowed_hosts=API_HOSTS,
            cookie=ScopedCookie(COOKIE, API_HOSTS),
            headers={"x-s": "private-signature"},
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "mime,body",
    [
        ("text/html", b"login"),
        ("application/json", b"[]"),
        ("application/json", b"private-invalid-json"),
        ("application/json", b"x" * (generic.MAX_BYTES + 1)),
    ],
)
def test_json_payload_is_bounded_and_validated(
    monkeypatch: pytest.MonkeyPatch, mime: str, body: bytes
) -> None:
    transport(
        monkeypatch,
        lambda request: httpx.Response(200, headers={"content-type": mime}, content=body),
    )
    with pytest.raises(ExtractionError) as error:
        fetch_json("https://edith.xiaohongshu.com/api", allowed_hosts=API_HOSTS)
    assert "private" not in str(error.value)


def test_platform_request_spacing_uses_monotonic_time(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(generic, "time", SimpleNamespace(monotonic=lambda: 100, sleep=waits.append))
    monkeypatch.setattr(generic.random, "uniform", lambda low, high: 1.25)
    context = PlatformRequests()
    context.wait()
    assert waits == []
    context.wait()
    assert waits == [1.25]
