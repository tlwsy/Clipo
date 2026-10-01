# SPDX-License-Identifier: AGPL-3.0-or-later
"""标注与阅读样式验收：真实临时 API/worker，原生 DOM 选区及离线读取。"""

import os
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright
from smoke_backup import ACCOUNT, RESULTS, launch, request


def select_text(page: Page, block: int, start: int, end: int) -> None:
    element = page.locator(f'[data-annotation-block="{block}"]')
    element.scroll_into_view_if_needed()
    element.evaluate(
        """(element, [start, end]) => {
          document.activeElement?.blur();
          const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
          const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
          function point(offset) {
            for (const node of nodes) {
              if (offset <= node.textContent.length) return [node, offset];
              offset -= node.textContent.length;
            }
            throw new Error('Invalid test range');
          }
          const range = document.createRange();
          range.setStart(...point(start)); range.setEnd(...point(end));
          const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
          document.dispatchEvent(new Event('selectionchange'));
        }""",
        [start, end],
    )
    expect(page.get_by_role("dialog", name="添加标注")).to_be_visible()


def wait_job(base: str, token: str, job: dict) -> int:
    for _ in range(200):
        status = request(base, "/jobs/" + job["job_id"], token)
        if status["status"] == "success":
            return status["note_id"]
        time.sleep(0.1)
    raise AssertionError("离线正文采集未完成")


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    blocks = [
        {
            "type": "text",
            "inlines": [
                {"text": "中文😀", "bold": True},
                {"text": "链接", "url": "https://example.com/reference"},
                {"text": "与加粗，选区必须保留原来的内容。"},
            ],
        },
        {"type": "list", "children": [{"type": "list_item", "text": "嵌套项目同样可以标注。"}]},
        {
            "type": "table",
            "children": [
                {"type": "table_row", "children": [{"type": "table_cell", "text": "单元格选区。"}]}
            ],
        },
        {
            "type": "details",
            "text": "更多内容",
            "children": [{"type": "text", "text": "折叠正文也保留位置。"}],
        },
        {"type": "code", "text": "const answer = 42;"},
        {"type": "text", "text": "另一段正文，需要与前面的选区分开标注。"},
    ]
    with tempfile.TemporaryDirectory(prefix="clipo-annotations-") as tmp, ExitStack() as stack:
        base = launch(stack, Path(tmp) / "instance")
        token = request(base, "/setup", body=ACCOUNT)["access_token"]
        note_id = wait_job(
            base,
            token,
            request(
                base,
                "/captures",
                token,
                {
                    "url": "https://example.com/annotations",
                    "payload": {
                        "title": "标注阅读验收",
                        "text": "离线标注验收。" * 20,
                        "blocks": blocks,
                    },
                },
            ),
        )
        legacy_id = wait_job(
            base,
            token,
            request(
                base,
                "/captures",
                token,
                {
                    "url": "https://example.com/legacy",
                    "payload": {"title": "旧正文", "text": "旧正文😀内容。\n\n第二段旧文字。"},
                },
            ),
        )
        path = f"/notes/{note_id}"
        with sync_playwright() as pw, ExitStack() as browsers:
            browser = pw.chromium.launch(
                headless=True, executable_path=os.environ.get("CLIPO_TEST_CHROMIUM")
            )
            browsers.callback(browser.close)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间").click()
            expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
            page.goto(base + path.replace("/notes/", "/notes/?id="))
            expect(page.get_by_role("heading", name="标注阅读验收")).to_be_visible()

            select_text(page, 0, 2, 6)
            page.get_by_role("button", name="黄色高亮").click()
            expect(page.get_by_role("button", name="我的标注（1）")).to_be_visible()
            saved = request(base, path, token)["annotations"]
            assert saved[0]["selected_text"] == "😀链接"
            assert saved[0]["start_offset"] == 2 and saved[0]["end_offset"] == 6
            expect(page.locator(f'mark[data-annotation-ids="{saved[0]["id"]}"]')).to_have_count(2)
            select_text(page, 0, 4, 8)
            page.get_by_role("button", name="添加批注", exact=True).click()
            page.get_by_label("批注内容").fill("私人想法 <script>不执行</script>")
            page.get_by_role("button", name="保存批注").click()
            expect(page.get_by_role("button", name="我的标注（2）")).to_be_visible()
            page.get_by_role("button", name="我的标注（2）").click()
            sidebar = page.get_by_role("complementary", name="我的标注")
            expect(sidebar.get_by_text("私人想法 <script>不执行</script>")).to_be_visible()
            first = sidebar.locator(".annotation-entry").first
            first.get_by_role("button", name="编辑标注").click()
            first.get_by_label("修改批注").fill("编辑后保留的批注")
            first.get_by_label("修改高亮颜色").select_option("green")
            first.get_by_role("button", name="保存修改").click()
            expect(first.get_by_text("编辑后保留的批注")).to_be_visible()
            expect(page.locator(".article-content .highlight-green").first).to_be_visible()
            sidebar.locator(".annotation-entry").last.get_by_role("button", name="删除标注").click()
            sidebar.get_by_role("button", name="确认删除标注").click()
            expect(page.get_by_role("button", name="我的标注（1）")).to_be_visible()
            sidebar.get_by_role("button", name="收起").click()

            for block in (2, 5, 8):
                select_text(page, block, 0, 3)
                page.get_by_role("button", name="蓝色高亮").click()
                expect(page.get_by_role("dialog", name="添加标注")).to_have_count(0)
            page.locator(".article-content summary").click()
            select_text(page, 7, 0, 4)
            page.get_by_role("button", name="粉色高亮").click()
            expect(page.get_by_role("button", name="我的标注（5）")).to_be_visible()
            page.locator(".article-content summary").click()
            page.get_by_role("button", name="我的标注（5）").click()
            sidebar.get_by_role("button", name="折叠正文", exact=True).click()
            expect(page.locator(".article-content details")).to_have_attribute("open", "")
            page.screenshot(path=str(RESULTS / "annotations-desktop.png"), full_page=True)
            sidebar.get_by_role("button", name="收起").click()

            page.get_by_role("button", name="阅读样式", exact=True).click()
            style = page.get_by_role("dialog", name="阅读样式")
            style.get_by_label("应用范围").select_option("global")
            style.get_by_role("button", name="专注", exact=True).click()
            style.get_by_role("button", name="保存样式").click()
            expect(style).to_have_count(0)
            expect(page.locator(".reading-surface")).to_have_css(
                "background-color", "rgb(28, 25, 23)"
            )
            page.get_by_role("button", name="阅读样式", exact=True).click()
            style.get_by_role("button", name="紧凑", exact=True).click()
            style.get_by_text("高级调整", exact=True).click()
            style.get_by_label("字号", exact=False).fill("22")
            style.get_by_label("对齐方式").select_option("justify")
            style.get_by_role("button", name="保存样式").click()
            expect(style).to_have_count(0)
            expect(page.locator(".article-content")).to_have_css("font-size", "22px")
            expect(page.locator(".article-content")).to_have_css("text-align", "justify")
            page.reload()
            expect(page.get_by_role("button", name="我的标注（5）")).to_be_visible()
            expect(page.locator(".article-content")).to_have_css("font-size", "22px")
            page.get_by_role("button", name="阅读样式", exact=True).click()
            style.get_by_role("button", name="本文跟随全局").click()
            expect(style).to_have_count(0)
            expect(page.locator(".reading-surface")).to_have_css(
                "background-color", "rgb(28, 25, 23)"
            )
            page.goto(base + f"/notes/?id={legacy_id}")
            expect(page.locator(".reading-surface")).to_have_css(
                "background-color", "rgb(28, 25, 23)"
            )
            select_text(page, 0, 3, 5)
            page.get_by_role("button", name="黄色高亮").click()
            expect(page.get_by_role("button", name="我的标注（1）")).to_be_visible()
            assert (
                request(base, f"/notes/{legacy_id}", token)["annotations"][0]["selected_text"]
                == "😀"
            )

            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(base + f"/notes/?id={note_id}")
            expect(page.get_by_role("button", name="我的标注（5）")).to_be_visible()
            page.get_by_role("button", name="我的标注（5）").click()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator(".note-reading").screenshot(path=str(RESULTS / "annotations-mobile.png"))
            sidebar.get_by_role("button", name="收起").click()
            page.get_by_role("button", name="阅读样式", exact=True).click()
            style.get_by_text("高级调整", exact=True).click()
            page.screenshot(path=str(RESULTS / "reading-style-mobile.png"))
            page.keyboard.press("Escape")
            expect(style).to_have_count(0)

            # Real network failure retains the chosen range and draft, and retry succeeds.
            select_text(page, 9, 0, 4)
            page.get_by_role("button", name="添加批注", exact=True).click()
            page.get_by_label("批注内容").fill("失败后仍然保留")
            page.route("**/api/v1/notes/*/annotations", lambda route: route.abort())
            page.get_by_role("button", name="保存批注").click()
            expect(page.get_by_role("dialog", name="添加标注").get_by_role("alert")).to_be_visible()
            expect(page.get_by_label("批注内容")).to_have_value("失败后仍然保留")
            page.unroute("**/api/v1/notes/*/annotations")
            page.get_by_role("button", name="保存批注").click()
            expect(page.get_by_role("button", name="我的标注（6）")).to_be_visible()

            # Cross-block selections are explicitly rejected without creating bad anchors.
            page.evaluate("""() => {
              document.activeElement?.blur();
              const start = document.querySelector('[data-annotation-block="0"]');
              const end = document.querySelector('[data-annotation-block="2"]');
              const range = document.createRange(); range.setStart(start, 0); range.setEnd(end, 1);
              const selection = getSelection();
              selection.removeAllRanges(); selection.addRange(range);
              document.dispatchEvent(new Event('selectionchange'));
            }""")
            expect(
                page.get_by_text("请在同一段、列表项或表格单元格内选择文字，跨段内容请分开标注。")
            ).to_be_visible()
            expect(page.get_by_role("dialog", name="添加标注")).to_have_count(0)
            page.evaluate("getSelection().removeAllRanges()")

            # No service worker is required for the existing in-app offline note cache.
            context.set_offline(True)
            page.get_by_role("link", name="全部笔记", exact=True).first.click()
            page.get_by_role("link", name="标注阅读验收", exact=False).first.click()
            expect(page.get_by_role("button", name="我的标注（6）")).to_be_visible()
            expect(page.locator(".reading-surface")).to_have_css(
                "background-color", "rgb(28, 25, 23)"
            )
            select_text(page, 9, 4, 8)
            page.get_by_role("button", name="黄色高亮").click()
            expect(
                page.get_by_role("dialog", name="添加标注").get_by_role("alert")
            ).to_contain_text("需要联网")
            context.set_offline(False)
            page.keyboard.press("Escape")
            share = request(base, path + "/shares", token, {"expires_in_days": 1})
            public = browser.new_context(viewport={"width": 390, "height": 844})
            shared = public.new_page()
            shared.goto(base + "/public/#" + share["token"])
            expect(shared.get_by_role("heading", name="标注阅读验收")).to_be_visible()
            expect(shared.locator("mark.annotation-mark")).to_have_count(0)
            expect(shared.get_by_text("编辑后保留的批注")).to_have_count(0)
            assert not errors, errors
            print(
                "标注 Chromium 验收通过：中文/emoji/富文本/嵌套/代码/旧正文选区、"
                "重叠、编辑删除、折叠定位、全局及本文样式、手机布局、"
                "失败重试、离线读取和公开页隔离。"
            )


if __name__ == "__main__":
    main()
