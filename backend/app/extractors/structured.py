# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small parsers shared by platform adapters; missing metadata stays empty."""

import json
import re
from datetime import UTC, datetime
from typing import Any

from lxml import etree
from lxml import html as lxml_html

from app.security.urls import UnsafeURL, normalize_url


def obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def count(value: Any) -> int:
    if type(value) is int or (isinstance(value, str) and value.isascii() and value.isdigit()):
        try:
            return min(max(int(value), 0), 2**31 - 1)
        except ValueError:
            pass
    return 0


def timestamp(value: Any) -> datetime | None:
    if type(value) not in (int, float) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000 if value >= 10**12 else value, tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def media_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return normalize_url("https:" + value if value.startswith("//") else value)
    except UnsafeURL:
        return None


def html_text(value: str) -> str:
    try:
        tree = lxml_html.fromstring(value)
        for node in tree.xpath("//script|//style|//iframe|//form"):
            node.drop_tree()
        return "\n".join(part.strip() for part in tree.itertext() if part.strip())
    except (etree.ParserError, ValueError):
        return ""


def script_object(html: str, name: str) -> dict[str, Any]:
    """Read a JSON assignment only, without evaluating any page JavaScript."""
    try:
        tree = lxml_html.fromstring(html)
    except (etree.ParserError, ValueError):
        return {}
    for script in tree.xpath("//script[not(@src)]/text()"):
        match = re.search(r"(?:^|[;\s])(?:var\s+|window\.)?" + re.escape(name) + r"\s*=\s*", script)
        if match:
            try:
                value, _ = json.JSONDecoder().raw_decode(script[match.end() :])
                return obj(value)
            except (ValueError, RecursionError):
                continue
    return {}
