# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest
from app.extractors.generic import parse_html
from app.extractors.site_name import site_name_from_html

HTML = (Path(__file__).parents[1] / "fixtures/site-name.html").read_text()


def test_generic_capture_preserves_explicit_site_name() -> None:
    content = parse_html(HTML, "https://example.com/article")
    assert content.site_name == "知识 & 阅读"
    assert content.title != content.site_name


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (None, None),
        ("<head><title>不是网站名称</title></head>", None),
        (
            '<meta property="og:site_name" content="  ">'
            '<meta name="application-name" content="备用">',
            "备用",
        ),
        ('<META NAME="OG:SITE_NAME" CONTENT="  A &amp; B\n  C  ">', "A & B C"),
        ('<head></head><body><meta property="og:site_name" content="正文伪造">', None),
        ('<body><meta property="og:site_name" content="正文伪造">', None),
        ('<meta property="og:site_name" content="' + "名" * 250 + '">', "名" * 200),
    ],
)
def test_site_metadata_fallback_and_bounds(html: str | None, expected: str | None) -> None:
    assert site_name_from_html(html) == expected
