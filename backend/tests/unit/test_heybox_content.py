# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import pytest
from app.content import CapturedBlock, ContentInline, blocks_markdown, walk_blocks
from app.extractors.base import CapturedContent, ExtractionError
from app.extractors.heybox_content import ArticleParser, article_url, enrich_games, parse_body
from app.extractors.xiaoheihe import HeyboxClient, XiaoheiheExtractor
from app.schemas.payload import CapturePayload
from pydantic import ValidationError

HTML = (Path(__file__).parents[1] / "fixtures/xiaoheihe-rich.html").read_text()


def test_html_keeps_order_nested_structure_captions_and_inline_marks() -> None:
    raw = [
        {"type": "html", "text": HTML},
        {"type": "img", "url": "https://imgheybox1.max-c.com/web/bbs/offline/one.png?thumbnail=1"},
    ]
    body, images, blocks, warnings = parse_body({"text": json.dumps(raw)})
    flat = list(walk_blocks(blocks))
    assert [b.type for b in blocks[:5]] == ["heading", "text", "image", "heading", "game_card"]
    assert images == ["https://imgheybox.max-c.com/web/bbs/offline/one.png"]
    assert sum(b.type == "image" for b in flat) == 2  # intentional second inline occurrence
    assert "步骤一：选择文件" in body and "尾部。" in body
    assert "private-script" not in body and "unsafe-frame" not in body
    assert blocks[1].inlines[1].bold
    assert any(s.url == "https://example.com/guide" for s in blocks[1].inlines)
    assert {"quote", "list", "list_item", "details", "table", "table_cell", "code"} <= {
        b.type for b in flat
    }
    assert not warnings
    markdown = blocks_markdown(blocks)
    assert "## 第一章" in markdown and "![步骤一：选择文件]" in markdown
    assert "**保存**" in markdown and "| 项目 | 结果 |" in markdown
    assert "    save()" in markdown


def test_text_links_newlines_stickers_and_local_upload_paths() -> None:
    raw = [
        {
            "type": "text",
            "text": '第一行[cube_惊讶]\n第二行😉<a href="https://example.com">说明</a>',
        },
        {
            "type": "img",
            "url": "https://example.com/photo.jpg",
            "text": "/storage/emulated/private.jpg",
        },
    ]
    body, _, blocks, _ = parse_body({"text": raw})
    assert body == "第一行[惊讶]\n第二行😉说明"
    assert blocks[-1].alt == ""
    assert blocks[0].inlines[-1].url == "https://example.com/"
    assert (
        article_url(
            "heybox://%7B%22protocol_type%22%3A%22openLink%22%2C%22link%22%3A%7B%22linkid%22%3A12%7D%7D"
        )
        == "https://www.xiaoheihe.cn/app/bbs/link/12"
    )
    assert article_url("www。example。com") is None


def test_unknown_blocks_keep_readable_fallback_and_report_partial_capture() -> None:
    body, _, blocks, warnings = parse_body(
        {"text": [{"type": "future", "text": "可读信息", "url": "https://example.com/extra"}]}
    )
    assert "可读信息" in body and blocks[-1].inlines[0].url
    assert warnings


def test_game_cards_require_matching_metadata_and_do_not_treat_epic_as_steam() -> None:
    blocks = [
        CapturedBlock(type="game_card", appid=value) for value in ("12345", "900000001", "99")
    ]
    incomplete = enrich_games(
        blocks,
        {
            "12345": {
                "steam_appid": 12345,
                "game_type": "pc",
                "name": "工具",
                "image": "https://heyboxbj.max-c.com/gameimg/steam_item_assets/a.jpg",
            },
            "900000001": {
                "steam_appid": 900000001,
                "game_type": "pc",
                "name": "另一商店",
                "image": "https://heyboxbj.max-c.com/gameimg/epic_game_image/b.jpg",
            },
            "99": {"steam_appid": 88, "name": "错误对象"},
        },
    )
    assert incomplete
    assert blocks[0].url == "https://store.steampowered.com/app/12345/"
    assert blocks[1].store == "epic" and blocks[1].url is None
    assert not blocks[2].text and blocks[2].url is None


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://127.0.0.1/x",
        "https://user:pass@example.com",
        "data:text/html,test",
    ],
)
def test_untrusted_blocks_cannot_supply_active_or_private_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        CapturePayload(title="标题", text="正文", blocks=[{"type": "image", "url": url}])
    with pytest.raises(ValidationError):
        ContentInline(text="链接", url=url)


def test_untrusted_content_is_bounded_and_legacy_notes_remain_readable() -> None:
    nested = {"type": "quote", "children": []}
    for _ in range(18):
        nested = {"type": "quote", "children": [nested]}
    with pytest.raises(ValidationError):
        CapturePayload(title="标题", text="正文", blocks=[nested])
    legacy = CapturedContent(url="https://example.com", title="旧笔记", text="旧正文")
    assert not legacy.blocks
    with pytest.raises(ValidationError):
        CapturedBlock(type="text", html="<script>bad()</script>")


def test_deep_html_is_reported_instead_of_recursing_forever() -> None:
    parser = ArticleParser()
    parser.fragment("<div>" * 40 + "正文" + "</div>" * 40)
    assert parser.warnings


def test_game_info_failure_does_not_lose_article(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.extractors import xiaoheihe

    url = "https://www.xiaoheihe.cn/app/bbs/link/123"
    monkeypatch.setattr(xiaoheihe, "fetch_html", lambda *args, **kwargs: ("<html></html>", url))
    monkeypatch.setattr(
        HeyboxClient,
        "page",
        lambda *args: {
            "link": {
                "linkid": 123,
                "title": "标题",
                "text": json.dumps(
                    [{"type": "text", "text": "重要正文"}, {"type": "game_card", "appid": "12345"}]
                ),
            }
        },
    )

    def fail(*args: object) -> dict:
        raise ExtractionError("上游失败")

    monkeypatch.setattr(HeyboxClient, "game_infos", fail)
    content = XiaoheiheExtractor(max_comments=0).extract(url)
    assert "重要正文" in content.text and content.capture_warnings
    assert content.extractor_version == 2
