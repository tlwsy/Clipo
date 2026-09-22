# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import socket
from pathlib import Path

import httpx
import pytest
from app.extractors import generic
from app.extractors.base import ExtractionError
from app.security.urls import UnsafeURL, normalize_url, public_addresses

HTML = (Path(__file__).parents[1] / "fixtures" / "article.html").read_text()


def test_extract_article_metadata_images_and_snapshot():
    content = generic.parse_html(HTML, "https://example.com/article")
    assert "知识笔记" in content.title
    assert "保留来源" in content.text
    assert "alert(" not in content.text
    assert "订阅推广" not in content.text
    assert content.author == "林舟"
    assert content.published_at.year == 2026
    assert content.images == ["https://example.com/cover.jpg", "https://example.com/reading.jpg"]
    assert content.raw_html == HTML


def test_readability_fallback(monkeypatch):
    monkeypatch.setattr(generic.trafilatura, "bare_extraction", lambda *args, **kwargs: None)
    content = generic.parse_html(HTML, "https://example.com")
    assert "保留来源" in content.text
    assert "alert(" not in content.text


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1",
        "http://[::1]",
        "http://169.254.169.254",
        "http://10.2.3.4",
        "http://[::ffff:127.0.0.1]",
        "http://localhost.",
        "http://service.local",
        "https://user:secret@example.com",
        "http://example.com:8000",
        "http://example.com\\@127.0.0.1",
        "https://exa\nmple.com",
    ],
)
def test_unsafe_urls_rejected(url):
    with pytest.raises(UnsafeURL):
        normalize_url(url)


def test_normalization_preserves_query_but_removes_fragment():
    assert (
        normalize_url(" HTTPS://Example.COM:443/article?b=2&a=1#chapter ")
        == "https://example.com/article?b=2&a=1"
    )


def test_all_dns_answers_are_checked(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (0, 0, 0, "", ("93.184.216.34", 443)),
            (0, 0, 0, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(UnsafeURL):
        public_addresses("https://example.com")


def mock_transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        generic.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: [(0, 0, 0, "", ("93.184.216.34", 443))]
    )


def test_fetch_pins_public_ip_preserves_host_sni_and_reads_fixture(monkeypatch):
    def handle(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=HTML)

    mock_transport(monkeypatch, handle)
    assert generic.fetch_html("https://example.com")[0] == HTML


def test_redirect_to_private_address_is_blocked_before_second_request(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    mock_transport(monkeypatch, handle)
    with pytest.raises(UnsafeURL):
        generic.fetch_html("https://example.com")
    assert len(requests) == 1


@pytest.mark.parametrize(
    "mime,body", [("application/pdf", b"pdf"), ("text/html", b"x" * (generic.MAX_BYTES + 1))]
)
def test_response_type_and_size_are_bounded(monkeypatch, mime, body):
    mock_transport(
        monkeypatch,
        lambda request: httpx.Response(200, headers={"content-type": mime}, content=body),
    )
    with pytest.raises(ExtractionError) as error:
        generic.fetch_html("https://example.com")
    assert not error.value.retryable
