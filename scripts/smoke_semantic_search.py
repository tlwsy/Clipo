# SPDX-License-Identifier: AGPL-3.0-or-later
"""语义搜索、设置、渐进结果、关键词降级与离线；临时实例和固定向量。"""

import os
import tempfile
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import Route, expect, sync_playwright
from smoke_annotations import wait_job
from smoke_backup import ACCOUNT, RESULTS, launch, request


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipo-search-") as temporary, ExitStack() as stack:
        base = launch(stack, Path(temporary) / "instance")
        token = request(
            base,
            "/setup",
            body={
                **ACCOUNT,
                "llm": {"api_key": "offline-only", "model": "offline-default"},
            },
        )["access_token"]
        title = "深度工作与专注力的关系"
        identifiers = []
        for index, name in enumerate((title, "美食烹饪教程")):
            identifiers.append(
                wait_job(
                    base,
                    token,
                    request(
                        base,
                        "/captures",
                        token,
                        {
                            "url": f"https://example.com/semantic/{index}",
                            "payload": {
                                "title": name,
                                "text": name + "。保存来源与完整原文。" * 12,
                                "tags": ["工作" if index == 0 else "生活"],
                            },
                        },
                    ),
                )
            )
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
            expect(page.locator(".note-card")).to_have_count(2)
            page.get_by_role("link", name="设置", exact=True).click()
            card = page.locator("#semantic-search")
            card.get_by_label("开启语义搜索").check()
            card.get_by_label("嵌入模型名称").fill("offline-embedding")
            card.get_by_role("button", name="保存语义搜索设置").click()
            expect(card.get_by_role("status")).to_contain_text("已保存")
            expect(card.get_by_label("语义索引状态")).to_contain_text("2 / 2 篇", timeout=30000)
            card.screenshot(path=str(RESULTS / "semantic-settings-desktop.png"))
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            card.screenshot(path=str(RESULTS / "semantic-settings-mobile.png"))
            card.get_by_role("button", name="补齐索引 / 重试失败").click()
            expect(card.get_by_role("status")).to_contain_text("有效向量不会重复生成")
            page.get_by_role("link", name="全部笔记", exact=True).click()
            query = page.get_by_label("搜索笔记")
            button = page.get_by_role("button", name="搜索", exact=True)
            query.fill("如何提高专注力")
            button.click()
            expect(page.locator(".search-match").first).to_have_text("语义匹配", timeout=30000)
            expect(page.locator(".note-card h2").first).to_have_text(title)
            page.screenshot(path=str(RESULTS / "semantic-results-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            query.fill(title)
            button.click()
            expect(page.locator(".search-match").first).to_have_text(
                "语义与关键词匹配", timeout=30000
            )
            expect(page.locator(".note-card h2 mark").first).to_have_text(title)
            page.get_by_label("按标签筛选").select_option(label="工作")
            expect(page.locator(".note-card")).to_have_count(1)
            page.get_by_label("按标签筛选").select_option("")
            query.fill('"' + title + '"')
            button.click()
            expect(page.locator(".search-match")).to_have_text("关键词匹配")

            # A superseded response must never overwrite the newly submitted query.
            held: list[Route] = []

            def delay(route: Route) -> None:
                if "旧问题" in route.request.url or "%E6%97%A7" in route.request.url:
                    held.append(route)
                else:
                    route.continue_()

            page.route("**/api/v1/notes/search?**", delay)
            query.fill("旧问题如何专注")
            button.click()
            page.wait_for_timeout(300)
            assert held
            query.fill("美食")
            button.click()
            expect(page.locator(".note-card h2")).to_have_text("美食烹饪教程")
            for route in held:
                route.abort()
            page.unroute("**/api/v1/notes/search?**", delay)
            expect(page.locator(".note-card h2")).to_have_text("美食烹饪教程")

            # Provider failure retains keyword results and the saved original/summary.
            page.get_by_role("link", name="设置", exact=True).click()
            card.get_by_label("嵌入模型名称").fill("offline-embedding-failure")
            card.get_by_role("button", name="保存语义搜索设置").click()
            expect(card.get_by_role("status")).to_contain_text("已保存")
            page.get_by_role("link", name="全部笔记", exact=True).click()
            query.fill(title)
            button.click()
            expect(
                page.get_by_text("语义搜索暂不可用，当前显示关键词结果；", exact=False)
            ).to_be_visible(timeout=30000)
            expect(page.locator(".search-match")).to_have_text("关键词匹配")
            page.locator(".note-card-link").click()
            expect(page.locator(".reader h1")).to_have_text(title)
            page.go_back()
            expect(query).to_have_value(title)

            expect(page.locator(".offline-status")).to_contain_text("离线可读 2", timeout=20000)
            context.set_offline(True)
            query.fill("深度工作")
            button.click()
            expect(
                page.get_by_text("当前离线，仅搜索此设备最近 50 篇缓存笔记", exact=False)
            ).to_be_visible()
            expect(page.locator(".search-match")).to_have_text("关键词匹配")
            expect(page.locator(".note-card h2")).to_have_text(title)
            context.set_offline(False)
            assert not errors, errors
            print(
                "语义设置、后台向量、混合标签、过滤、精确短语、取消、失败降级、离线与手机布局通过"
            )


if __name__ == "__main__":
    main()
