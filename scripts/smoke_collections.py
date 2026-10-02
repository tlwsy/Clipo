# SPDX-License-Identifier: AGPL-3.0-or-later
"""空间系统离线浏览器验收：真实临时 API/worker，桌面与手机视口。"""

import os
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright
from smoke_backup import ACCOUNT, RESULTS, launch, request


def create_space(page: Page, name: str) -> None:
    page.get_by_role("button", name="创建空间", exact=True).click()
    dialog = page.get_by_role("dialog", name="创建空间", exact=True)
    dialog.get_by_label("空间名称").fill(name)
    dialog.get_by_label("紫色", exact=True).check()
    dialog.get_by_label("图标", exact=True).select_option("book")
    dialog.get_by_role("button", name="保存空间").click()
    expect(dialog).to_have_count(0)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="clipo-collections-") as temporary,
        ExitStack() as stack,
    ):
        base = launch(stack, Path(temporary) / "instance")
        token = request(base, "/setup", body=ACCOUNT)["access_token"]
        jobs = [
            request(
                base,
                "/captures",
                token,
                {
                    "url": f"https://example.com/collections/{index}",
                    "payload": {
                        "title": f"空间验收 {index:02}",
                        "text": "仅使用本地离线数据验证空间组织。" * 5,
                    },
                },
            )
            for index in range(27)
        ]
        for job in jobs:
            for _ in range(200):
                status = request(base, "/jobs/" + job["job_id"], token)
                if status["status"] == "success":
                    break
                time.sleep(0.1)
            assert status["status"] == "success"
        with sync_playwright() as playwright, ExitStack() as browser_stack:
            browser = playwright.chromium.launch(
                headless=True, executable_path=os.environ.get("CLIPO_TEST_CHROMIUM")
            )
            browser_stack.callback(browser.close)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间").click()
            expect(page.locator(".note-card")).to_have_count(24)
            page.get_by_role("link", name="空间", exact=True).click()
            expect(page.get_by_text("创建你的第一个空间")).to_be_visible()
            create_space(page, "工作")
            card = page.locator(".collection-card").filter(has_text="工作")
            expect(card).to_contain_text("0 篇笔记")
            page.get_by_role("button", name="编辑空间 工作", exact=True).click()
            page.get_by_role("dialog").get_by_label("空间名称").fill("研究")
            page.get_by_role("dialog").get_by_role("button", name="保存空间").click()
            expect(page.get_by_role("heading", name="研究", exact=True)).to_be_visible()
            create_space(page, "读书")
            page.get_by_role("button", name="创建空间", exact=True).click()
            page.get_by_label("空间名称").fill("研究")
            page.get_by_role("button", name="保存空间", exact=True).click()
            expect(page.get_by_role("dialog").get_by_role("alert")).to_contain_text("同名")
            page.keyboard.press("Escape")
            expect(page.get_by_role("dialog")).to_have_count(0)
            page.get_by_role("link", name="全部笔记", exact=True).click()
            page.get_by_role("button", name="多选笔记").click()
            page.locator(".note-selection input").nth(0).check()
            page.locator(".note-selection input").nth(1).check()
            page.get_by_role("button", name="添加到空间", exact=True).click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_label("研究", exact=True).check()
            dialog.get_by_label("读书", exact=True).check()
            dialog.get_by_role("button", name="保存归属").click()
            expect(page.get_by_text("空间归属已保存。", exact=True)).to_be_visible()
            page.get_by_role("link", name="空间", exact=True).click()
            card = page.locator(".collection-card").filter(has_text="研究")
            expect(card).to_contain_text("2 篇笔记")
            card.get_by_role("link").click()
            expect(page.locator(".note-card")).to_have_count(2)
            page.get_by_role("button", name="添加笔记", exact=True).click()
            dialog = page.get_by_role("dialog")
            expect(dialog.locator(".collection-options input")).to_have_count(24)
            for checkbox in dialog.locator(".collection-options input").all():
                checkbox.check()
            dialog.get_by_role("button", name="加载更多笔记").click()
            expect(dialog.locator(".collection-options input")).to_have_count(27)
            for checkbox in dialog.locator(".collection-options input").all():
                checkbox.check()
            dialog.get_by_role("button", name="添加所选笔记").click()
            expect(page.get_by_text("27 篇笔记", exact=True)).to_be_visible()
            expect(page.locator(".note-card")).to_have_count(24)
            page.get_by_role("button", name="加载更多", exact=True).click()
            expect(page.locator(".note-card")).to_have_count(27)
            page.locator(".note-card").first.get_by_role("link").click()
            page.get_by_role("button", name="管理所属空间").click()
            dialog = page.get_by_role("dialog")
            expect(dialog.get_by_label("研究", exact=True)).to_be_checked()
            expect(dialog.get_by_label("读书", exact=True)).to_be_checked()
            dialog.get_by_label("研究", exact=True).uncheck()
            dialog.get_by_role("button", name="保存归属").click()
            page.get_by_role("button", name="管理所属空间").click()
            create_space(page, "快速空间")
            dialog = page.get_by_role("dialog")
            expect(dialog.get_by_label("快速空间", exact=True)).to_be_checked()
            dialog.get_by_label("搜索空间").fill("快速")
            expect(dialog.locator(".collection-options input")).to_have_count(1)
            dialog.get_by_role("button", name="保存归属").click()
            page.set_viewport_size({"width": 390, "height": 844})
            page.get_by_role("link", name="空间", exact=True).click()
            card = page.locator(".collection-card").filter(has_text="研究")
            expect(card).to_contain_text("26 篇笔记")
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), "手机页面横向溢出"
            page.screenshot(path=str(RESULTS / "collections-mobile.png"), full_page=True)
            card.get_by_role("link").click()
            page.locator(".note-card").first.get_by_role("button", name="从空间移除").click()
            expect(page.get_by_text("25 篇笔记", exact=True)).to_be_visible()
            page.get_by_role("button", name="编辑空间", exact=True).click()
            page.screenshot(path=str(RESULTS / "collection-edit-mobile.png"))
            page.keyboard.press("Escape")
            page.get_by_role("button", name="删除空间", exact=True).click()
            page.get_by_role("button", name="确认删除空间").click()
            expect(page.get_by_role("heading", name="空间", exact=True)).to_be_visible()
            assert len(request(base, "/notes?limit=100", token)["items"]) == 27
            assert len(request(base, "/collections", token)["collections"]) == 2
            # Network failures retain an actionable close/retry path and never report success.
            page.route("**/api/v1/collections", lambda route: route.abort())
            page.get_by_role("link", name="全部笔记", exact=True).click()
            page.locator(".note-card").first.get_by_role("link").click()
            page.get_by_role("button", name="管理所属空间").click()
            expect(page.get_by_role("dialog").get_by_role("alert")).to_be_visible()
            expect(
                page.get_by_role("dialog").get_by_role("button", name="保存归属")
            ).to_be_disabled()
            page.keyboard.press("Escape")
            assert not errors, errors
            print(
                "空间 Chromium 验收通过：CRUD、多空间、批量、双向分页、快速创建、"
                "单篇预勾选/移除、失败状态、手机布局；无脚本错误。"
            )


if __name__ == "__main__":
    main()
