# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read explicit site metadata without loading a page or inferring from its title."""

from html.parser import HTMLParser


def clean_site_name(value: str | None) -> str | None:
    return " ".join((value or "").replace("\x00", "").split())[:200] or None


class _HeadComplete(Exception):
    pass


class _SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.names: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "body":
            raise _HeadComplete
        if tag != "meta":
            return
        attributes = dict(attrs)
        key = (attributes.get("property") or attributes.get("name") or "").strip().lower()
        value = clean_site_name(attributes.get("content"))
        if key in {"og:site_name", "application-name"} and value:
            self.names.setdefault(key, value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            raise _HeadComplete


def site_name_from_html(html: str | None) -> str | None:
    if not html:
        return None
    parser = _SiteParser()
    try:
        # Old notes can have multi-megabyte snapshots. Only inspect the head prefix.
        parser.feed(html[:131072])
    except (_HeadComplete, ValueError, AssertionError):
        pass
    return parser.names.get("og:site_name") or parser.names.get("application-name")
