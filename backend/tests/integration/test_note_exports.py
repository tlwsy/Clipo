# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import UTC, datetime
from urllib.parse import unquote

import pytest
from app.extractors.base import CapturedContent
from app.llm.orchestrator import CommentScore, Summary, SummaryResult
from app.models import Annotation
from app.note_repository import NoteRepository
from app.repositories import IdentityRepository
from app.security.credentials import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from lxml import html
from markdown_it import MarkdownIt
from test_note_organization import seed_note


def seed_export_note(app: FastAPI) -> int:
    with app.state.session_factory.begin() as db:
        repository = NoteRepository(db, 1)
        job = repository.create_job("https://example.com/export", None)
        repository.claim(job.id, "test-export")
        content = CapturedContent.model_validate(
            {
                "url": job.url,
                "title": "中文笔记😀 <script>alert(1)</script>\r\n/标题",
                "text": "旧版纯文本不应代替有序正文",
                "site_name": "测试站点",
                "author": "作者<script>不执行</script>",
                "published_at": "2026-10-01T08:00:00Z",
                "selection": "保存时的选区内容",
                "raw_html": "RAW_HTML_SECRET_MUST_NOT_EXPORT",
                "images": ["https://example.com/photo.png", "https://example.com/extra.png"],
                "blocks": [
                    {
                        "type": "text",
                        "inlines": [{"text": "中😀链接", "bold": True}, {"text": "尾"}],
                    },
                    {"type": "heading", "text": "小标题", "level": 3},
                    {"type": "image", "url": "https://example.com/photo.png", "alt": "配图"},
                    {
                        "type": "list",
                        "ordered": True,
                        "children": [{"type": "list_item", "text": "嵌套列表"}],
                    },
                    {"type": "quote", "text": "引用段落"},
                    {"type": "code", "text": "print('<script>')\n```"},
                    {
                        "type": "table",
                        "children": [
                            {
                                "type": "table_row",
                                "children": [
                                    {"type": "table_cell", "text": "表头", "header": True}
                                ],
                            },
                            {
                                "type": "table_row",
                                "children": [{"type": "table_cell", "text": "表格内容|换行\n次行"}],
                            },
                        ],
                    },
                    {
                        "type": "details",
                        "text": "折叠标题",
                        "children": [{"type": "text", "text": "展开后正文"}],
                    },
                    {"type": "divider"},
                    {
                        "type": "game_card",
                        "text": "游戏名称",
                        "url": "https://store.steampowered.com/app/42/",
                    },
                ],
                "comments": [
                    {
                        "author": "评论作者",
                        "content": "有价值的评论 <img src=x onerror=alert(1)>",
                        "source_id": "good",
                    },
                    {"content": "低分私有评论不可导出", "source_id": "hidden"},
                    {"content": "有价值的回复", "parent_source_id": "hidden"},
                ],
            }
        )
        repository.finish(
            job.id,
            "test-export",
            content,
            SummaryResult(
                Summary(
                    summary_markdown="**摘要重点**\n\n<script>无脚本</script>",
                    key_points=["记住这一点"],
                    suggested_tags=["导出"],
                ),
                comment_scores=[
                    CommentScore(index=0, score=0.9, reason="有帮助"),
                    CommentScore(index=1, score=0.1, reason="低分"),
                    CommentScore(index=2, score=0.8, reason="有补充"),
                ],
            ),
            False,
        )
        return job.note_id


@pytest.mark.parametrize("format", ["markdown", "html"])
def test_complete_export_is_private_inert_and_preserves_content(
    app: FastAPI, client: TestClient, auth: dict, format: str
) -> None:
    note_id = seed_export_note(app)
    path = f"/api/v1/notes/{note_id}"
    for block, start, end, selected in [(0, 1, 4, "😀链"), (4, 0, 2, "嵌套"), (11, 0, 2, "表格")]:
        response = client.post(
            path + "/annotations",
            headers=auth,
            json={
                "block_index": block,
                "start_offset": start,
                "end_offset": end,
                "selected_text": selected,
                "highlight_color": "green",
                "note_text": "私人笔记<script>禁止执行</script>",
            },
        )
        assert response.status_code == 201, response.text
    before = client.get(path, headers=auth).json()
    response = client.get(path + f"/export/{format}", headers=auth)
    assert response.status_code == 200, response.text
    text = response.text
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["content-type"].startswith("text/" + format)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "中文笔记😀" in unquote(response.headers["content-disposition"])
    assert "\r" not in response.headers["content-disposition"]
    for value in (
        "测试站点",
        "2026-10-01",
        "摘要重点",
        "记住这一点",
        "保存时的选区内容",
        "有价值的评论",
        "有价值的回复",
        "私人笔记",
        "photo.png",
        "extra.png",
        "游戏名称",
        "展开后正文",
    ):
        assert value in text.replace("\\", "")
    for value in (
        "RAW_HTML_SECRET",
        "低分私有评论不可导出",
        "旧版纯文本不应",
    ):
        assert value not in text
    rendered = (
        MarkdownIt("commonmark", {"html": True}).enable("table").render(text)
        if format == "markdown"
        else text
    )
    assert not html.fromstring(rendered).xpath(
        "//script|//iframe|//object|//*[@onerror or @onload]"
    )
    assert client.get(path, headers=auth).json() == before
    if format == "html":
        document = html.fromstring(text)
        assert not document.xpath("//script|//iframe|//object")
        assert not document.xpath("//*[@onerror or @onload]")
        assert document.xpath('//mark[@class="highlight-green"]')
        assert document.xpath("//ol/li") and document.xpath("//table//th")
        assert document.xpath("//pre/code")[0].text == "print('<script>')\n```"
        assert len(document.xpath('//img[@src="https://example.com/photo.png"]')) == 1
        assert "@page" in text and "counter(page)" in text and "@media print" in text
    else:
        assert "1. 嵌套列表" in text and "### 小标题" in text
        assert "| 表头 |" in text and "\\|换行<br>次行" in text
        assert "````" in text and "UTF-16 偏移 1–4" in text


@pytest.mark.parametrize("format", ["markdown", "html"])
def test_export_options_ownership_missing_notes_and_legacy_content(
    app: FastAPI, client: TestClient, auth: dict, format: str
) -> None:
    note_id = seed_note(app)
    path = f"/api/v1/notes/{note_id}"
    client.post(
        path + "/annotations",
        headers=auth,
        json={
            "block_index": 0,
            "start_offset": 0,
            "end_offset": 2,
            "highlight_color": "yellow",
            "note_text": "不应泄露的私人笔记",
        },
    )
    endpoint = path + f"/export/{format}"
    complete = client.get(endpoint, headers=auth).text
    assert "未生成摘要" in complete and "不应泄露的私人笔记" in complete
    assert "暂无标记为有价值的评论" in complete
    without = client.get(
        endpoint,
        headers=auth,
        params={
            "include_summary": False,
            "include_comments": False,
            "include_annotations": False,
        },
    )
    assert without.status_code == 200
    for value in ("未生成摘要", "有价值评论", "不应泄露的私人笔记", "我的标注与笔记", "<mark "):
        assert value not in without.text
    assert "整理笔记" in without.text
    for option, absent, retained in (
        ("include_summary", "未生成摘要", "我的标注与笔记"),
        ("include_comments", "暂无标记为有价值的评论", "未生成摘要"),
        ("include_annotations", "不应泄露的私人笔记", "未生成摘要"),
    ):
        body = client.get(endpoint, headers=auth, params={option: False}).text
        assert absent not in body and retained in body
    with app.state.session_factory.begin() as db:
        IdentityRepository(db).create_user("other", "other@example.com", "unused", False)
        db.add(
            Annotation(
                user_id=2,
                note_id=note_id,
                block_index=0,
                start_offset=0,
                end_offset=2,
                selected_text="整理",
                note_text="跨账号损坏数据",
                created_at=datetime.now(UTC),
            )
        )
    other = {"Authorization": "Bearer " + create_access_token(2, app.state.settings)}
    assert "跨账号损坏数据" not in client.get(endpoint, headers=auth).text
    assert client.get(endpoint, headers=other).status_code == 404
    assert client.get(endpoint).status_code == 401
    assert (
        client.get(endpoint, headers=auth, params={"include_summary": "invalid"}).status_code == 422
    )
    assert client.get(endpoint, headers=auth, params={"unknown": "value"}).status_code == 422
    client.delete(path, headers=auth)
    assert client.get(endpoint, headers=auth).status_code == 404


def test_stale_annotations_remain_in_list_but_are_not_relocated(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    note_id = seed_note(app)
    with app.state.session_factory.begin() as db:
        db.add(
            Annotation(
                user_id=1,
                note_id=note_id,
                block_index=0,
                start_offset=0,
                end_offset=2,
                selected_text="旧文",
                highlight_color="pink",
                note_text="旧批注",
            )
        )
    response = client.get(f"/api/v1/notes/{note_id}/export/html", headers=auth)
    assert response.status_code == 200
    assert "原文位置已失效" in response.text and "旧批注" in response.text
    assert "<mark " not in response.text


def test_export_contract_describes_text_success_and_json_errors(app: FastAPI) -> None:
    for format in ("markdown", "html"):
        operation = app.openapi()["paths"][f"/api/v1/notes/{{note_id}}/export/{format}"]["get"]
        assert set(operation["responses"]["200"]["content"]) == {"text/" + format}
        assert set(operation["responses"]["401"]["content"]) == {"application/json"}
