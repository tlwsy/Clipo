# SPDX-License-Identifier: AGPL-3.0-or-later
"""单篇下载、PDF 预览与实际 PDF 渲染；临时 API/worker，固定模型和图片。"""

import os
import tempfile
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import Route, expect, sync_playwright
from smoke_annotations import wait_job
from smoke_backup import ACCOUNT, RESULTS, launch, request


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="clipo-export-smoke-") as temporary,
        ExitStack() as stack,
    ):
        base = launch(stack, Path(temporary) / "instance")
        token = request(
            base,
            "/setup",
            body={
                **ACCOUNT,
                "llm": {
                    "api_key": "offline-only",
                    "model": "offline-hostile",
                    "comment_score_threshold": 0.8,
                },
            },
        )["access_token"]
        blocks = [
            {
                "type": "text",
                "inlines": [
                    {"text": "中文😀", "bold": True},
                    {"text": "链接", "url": "https://example.com/reference"},
                    {"text": "正文；高亮不会改变原始顺序。"},
                ],
            },
            {"type": "image", "url": "https://example.com/photo.svg", "alt": "离线图片样本"},
            {
                "type": "table",
                "children": [
                    {
                        "type": "table_row",
                        "children": [{"type": "table_cell", "text": "测试表头", "header": True}],
                    },
                    {
                        "type": "table_row",
                        "children": [{"type": "table_cell", "text": "测试单元格"}],
                    },
                ],
            },
            {
                "type": "details",
                "text": "原本折叠的内容",
                "children": [{"type": "text", "text": "导出时完整展开。"}],
            },
            {"type": "code", "text": 'console.log("<script>普通文字</script>")'},
            *[
                {
                    "type": "text",
                    "text": f"第 {i + 1} 段：" + "保存完整正文与出处，中文长文应自然分页。" * 8,
                }
                for i in range(32)
            ],
        ]
        note_id = wait_job(
            base,
            token,
            request(
                base,
                "/captures",
                token,
                {
                    "url": "https://example.com/export-smoke",
                    "payload": {
                        "title": "中文导出验收😀",
                        "text": "单篇多格式导出离线样本。" * 20,
                        "blocks": blocks,
                        "images": [
                            "https://example.com/photo.svg",
                            "https://example.com/missing.png",
                        ],
                        "comments": [
                            {
                                "author": "高价值读者",
                                "content": "保存来源和操作步骤的高价值建议。",
                                "likes": 20,
                            },
                            {
                                "author": "低分读者",
                                "content": "这条低分评论不应该出现在导出文件中。",
                                "likes": 3,
                            },
                        ],
                    },
                },
            ),
        )
        for start, end, color, text in [
            (2, 6, "yellow", "第一条私人批注"),
            (4, 8, "blue", "<script>第二条私人批注</script>"),
        ]:
            request(
                base,
                f"/notes/{note_id}/annotations",
                token,
                {
                    "block_index": 0,
                    "start_offset": start,
                    "end_offset": end,
                    "highlight_color": color,
                    "note_text": text,
                },
            )
        with sync_playwright() as pw, ExitStack() as browsers:
            browser = pw.chromium.launch(
                headless=True, executable_path=os.environ.get("CLIPO_TEST_CHROMIUM")
            )
            browsers.callback(browser.close)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})

            def media(route: Route) -> None:
                if route.request.url.endswith("photo.svg"):
                    route.fulfill(
                        content_type="image/svg+xml",
                        body=(
                            '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="140">'
                            '<rect width="600" height="140" fill="#d1fae5"/>'
                            '<text x="30" y="80" font-size="24">'
                            "Clipo offline image fixture</text></svg>"
                        ),
                    )
                else:
                    route.abort()

            context.route("https://example.com/**", media)
            page = context.new_page()
            errors: list[str] = []
            refreshes: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda req: (
                    refreshes.append(req.url) if req.url.endswith("/auth/refresh") else None
                ),
            )
            page.goto(base + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间").click()
            expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
            page.goto(base + f"/notes/?id={note_id}")
            expect(page.get_by_role("heading", name="中文导出验收😀")).to_be_visible()
            page.get_by_role("button", name="导出笔记", exact=True).click()
            menu = page.get_by_role("dialog", name="导出笔记", exact=True)
            expect(menu.get_by_label("包含私人标注")).to_be_checked()
            with page.expect_download() as downloading:
                menu.get_by_role("button", name="导出为 Markdown").click()
            download = downloading.value
            assert download.suggested_filename == f"中文导出验收😀-{note_id}.md"
            markdown_path = RESULTS / "note-export.md"
            download.save_as(markdown_path)
            markdown = markdown_path.read_text()
            assert "第一条私人批注" in markdown and "高价值建议" in markdown
            assert "这条低分评论" not in markdown
            assert "UTF-16 偏移 2–6" in markdown and "第 32 段" in markdown

            # A real cookie refresh retries the text download through the common API client.
            expiry = [True]
            html_route = "**/api/v1/notes/*/export/html?**"

            def expire_once(route: Route) -> None:
                if expiry[0]:
                    expiry[0] = False
                    route.fulfill(
                        status=401,
                        content_type="application/json",
                        body='{"error":{"code":"expired","message":"测试过期"}}',
                    )
                else:
                    route.continue_()

            page.route(html_route, expire_once)
            refresh_count = len(refreshes)
            with page.expect_download() as downloading:
                menu.get_by_role("button", name="导出为 HTML", exact=True).click()
            download = downloading.value
            assert len(refreshes) == refresh_count + 1
            html_path = RESULTS / "note-export.html"
            download.save_as(html_path)
            document = html_path.read_text()
            assert "<mark " in document and "第一条私人批注" in document
            page.unroute(html_route)

            # Failed downloads retain the options and can be retried.
            md_route = "**/api/v1/notes/*/export/markdown?**"
            page.route(md_route, lambda route: route.abort())
            menu.get_by_role("button", name="导出为 Markdown").click()
            expect(menu.get_by_role("alert")).to_be_visible()
            expect(menu.get_by_label("包含私人标注")).to_be_checked()
            page.unroute(md_route)
            menu.get_by_label("包含私人标注").uncheck()
            menu.get_by_label("包含 AI 摘要").uncheck()
            menu.get_by_label("包含有价值评论").uncheck()
            with page.expect_download() as downloading:
                menu.get_by_role("button", name="导出为 HTML", exact=True).click()
            private_free = Path(downloading.value.path()).read_text()
            for value in ("第一条私人批注", "第二条私人批注", "<mark ", "AI 摘要", "有价值评论"):
                assert value not in private_free
            for label in ("包含私人标注", "包含 AI 摘要", "包含有价值评论"):
                menu.get_by_label(label).check()

            menu.get_by_role("button", name="导出为 PDF").click()
            preview = page.get_by_role("dialog", name="PDF 打印预览")
            iframe = page.frame_locator('iframe[title="笔记打印预览"]')
            printing = preview.get_by_role("button", name="打印 / 保存为 PDF")
            expect(printing).to_be_enabled()
            expect(iframe.get_by_role("heading", name="中文导出验收😀")).to_be_visible()
            expect(iframe.get_by_text("第一条私人批注", exact=True)).to_have_count(1)
            expect(iframe.locator("script, iframe, [onerror]")).to_have_count(0)
            expect(iframe.locator(".highlight-blue").first).to_have_css(
                "background-color", "rgb(219, 234, 254)"
            )
            assert (
                page.locator("iframe").get_attribute("sandbox") == "allow-same-origin allow-modals"
            )
            page.screenshot(path=str(RESULTS / "note-export-preview-desktop.png"))
            page.locator("iframe").evaluate("""frame => {
                  window.exportPrinted = false;
                  frame.contentWindow.addEventListener('beforeprint', () => {
                    window.exportPrinted = true;
                  });
                }""")
            printing.click()
            assert page.evaluate(
                "window.exportPrinted === true"
            ), "iframe 未收到真实 beforeprint 事件"
            expect(preview.get_by_role("status")).to_contain_text("已请求浏览器打印")

            # Option changes invalidate the prior preview immediately.
            preview.get_by_label("包含私人标注").uncheck()
            expect(printing).to_be_enabled()
            expect(iframe.locator("mark")).to_have_count(0)
            expect(iframe.get_by_text("第一条私人批注", exact=True)).to_have_count(0)
            preview.get_by_label("包含私人标注").check()
            expect(printing).to_be_enabled()
            expect(iframe.get_by_text("第一条私人批注", exact=True)).to_have_count(1)

            # Pending responses cannot leave a stale private preview printable.
            held: list[Route] = []

            def delay_private_free(route: Route) -> None:
                if "include_annotations=false" in route.request.url:
                    held.append(route)
                else:
                    route.continue_()

            page.route(html_route, delay_private_free)
            with page.expect_request(lambda req: "include_annotations=false" in req.url):
                preview.get_by_label("包含私人标注").uncheck()
            expect(printing).to_be_disabled()
            expect(page.locator("iframe")).to_have_count(0)
            preview.get_by_label("包含私人标注").check()
            expect(printing).to_be_enabled()
            expect(iframe.get_by_text("第一条私人批注", exact=True)).to_have_count(1)
            assert held
            for route in held:
                route.abort()
            page.unroute(html_route)

            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert preview.evaluate("el => el.scrollWidth <= el.clientWidth")
            page.screenshot(path=str(RESULTS / "note-export-preview-mobile.png"))
            preview.get_by_role("button", name="取消", exact=True).click()
            expect(preview).to_have_count(0)
            page.get_by_role("button", name="导出笔记", exact=True).click()
            page.screenshot(path=str(RESULTS / "note-export-menu-mobile.png"))

            # PDF failures are visible, and reopening/retrying never shows an old preview.
            page.route(
                html_route,
                lambda route: route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"error":{"code":"unavailable","message":"测试服务暂不可用"}}',
                ),
            )
            menu.get_by_role("button", name="导出为 PDF").click()
            expect(preview.get_by_role("alert")).to_contain_text("测试服务暂不可用")
            expect(printing).to_be_disabled()
            expect(page.locator("iframe")).to_have_count(0)
            page.unroute(html_route)
            preview.get_by_role("button", name="重新加载预览").click()
            expect(printing).to_be_enabled()
            page.keyboard.press("Escape")
            expect(preview).to_have_count(0)

            # A stalled external image stops after a bounded wait, with an explicit notice.
            delayed_images: list[Route] = []
            page.route("https://example.com/photo.svg", lambda route: delayed_images.append(route))
            page.get_by_role("button", name="导出笔记", exact=True).click()
            menu.get_by_role("button", name="导出为 PDF").click()
            expect(preview.get_by_role("status")).to_contain_text("部分图片加载超时", timeout=12000)
            expect(printing).to_be_enabled()
            assert delayed_images
            for route in delayed_images:
                route.abort()
            page.unroute("https://example.com/photo.svg")
            preview.get_by_role("button", name="取消", exact=True).click()

            context.set_offline(True)
            page.get_by_role("button", name="导出笔记", exact=True).click()
            menu.get_by_role("button", name="导出为 Markdown").click()
            expect(menu.get_by_role("alert")).to_contain_text("需要联网")
            context.set_offline(False)
            page.keyboard.press("Escape")

            # Open the downloaded document independently and render a real multi-page PDF.
            standalone = context.new_page()
            standalone.on("pageerror", lambda error: errors.append(str(error)))
            standalone.goto(html_path.resolve().as_uri())
            expect(standalone.get_by_role("heading", name="中文导出验收😀")).to_be_visible()
            expect(standalone.locator("script, iframe, [onerror]")).to_have_count(0)
            assert standalone.evaluate("typeof window.clipoXss") == "undefined"
            standalone.emulate_media(media="print")
            pdf = standalone.pdf(
                path=str(RESULTS / "note-export.pdf"),
                print_background=True,
                prefer_css_page_size=True,
            )
            assert pdf.startswith(b"%PDF-") and len(pdf) > 10000
            assert not errors, errors
            print(
                "单篇导出 Chromium 验收通过：Markdown/HTML 下载、真实续期、私人内容开关、"
                "失败重试、离线提示、PDF 预览和真实 beforeprint、"
                "独立 HTML 与 PDF 渲染、390px 布局及无脚本执行。"
            )


if __name__ == "__main__":
    main()
