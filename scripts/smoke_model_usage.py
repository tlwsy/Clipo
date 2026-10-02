# SPDX-License-Identifier: AGPL-3.0-or-later
"""月度模型限额设置、真实 worker 拦截与恢复；仅使用离线模型。"""

import os
import tempfile
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from smoke_annotations import wait_job
from smoke_backup import ACCOUNT, RESULTS, launch, request


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipo-quota-") as temporary, ExitStack() as stack:
        base = launch(stack, Path(temporary) / "instance")
        token = request(
            base,
            "/setup",
            body={**ACCOUNT, "llm": {"api_key": "offline-only", "model": "offline-default"}},
        )["access_token"]
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
            expect(page.get_by_role("heading", name="你的笔记", exact=False)).to_be_visible()
            page.goto(base + "/settings/")
            panel = page.get_by_role("region", name="模型月度用量")
            field = panel.get_by_label("每月最多调用次数")
            usage = panel.get_by_label("本月模型用量")
            expect(usage).to_contain_text("当前不限")
            field.fill("0")
            panel.get_by_role("button", name="保存月度限额").click()
            expect(panel.get_by_role("status")).to_contain_text("已保存")
            expect(usage).to_contain_text("上限 0 次")
            page.reload()
            expect(field).to_have_value("0")
            # Capture persists the original without a model call while paused.
            note = wait_job(
                base,
                token,
                request(
                    base,
                    "/captures",
                    token,
                    {
                        "url": "https://example.com/quota",
                        "payload": {"title": "额度测试笔记", "text": "保留出处，并定期回顾。"},
                    },
                ),
            )
            saved = request(base, f"/notes/{note}", token)
            assert saved["status"] == "original_only"
            assert "本月模型调用次数" in saved["summary_error"]
            assert request(base, "/settings/model-usage", token)["calls"] == 0
            field.fill("1")
            panel.get_by_role("button", name="保存月度限额").click()
            expect(usage).to_contain_text("上限 1 次")
            page.goto(base + f"/notes/?id={note}")
            page.get_by_role("button", name="打开 AI 对话").click()
            conversation = page.get_by_role("region", name="私人 AI 对话")
            page.get_by_label("向 AI 提问").fill("主要论点是什么？")
            page.get_by_role("button", name="发送问题").click()
            expect(conversation.locator(".conversation-message.assistant")).to_have_count(
                1, timeout=20000
            )
            page.get_by_label("向 AI 提问").fill("如何执行？")
            page.get_by_role("button", name="发送问题").click()
            expect(conversation.get_by_text("本月模型调用次数", exact=False)).to_be_visible(
                timeout=20000
            )
            expect(conversation.get_by_role("button", name="重试回答")).to_be_visible()
            assert request(base, "/settings/model-usage", token)["calls"] == 1
            page.goto(base + "/settings/")
            expect(usage).to_contain_text("剩余 0 次")
            field.fill("2")
            panel.get_by_role("button", name="刷新用量").click()
            expect(panel.get_by_role("button", name="刷新用量")).to_be_enabled()
            expect(field).to_have_value("2")
            panel.get_by_role("button", name="保存月度限额").click()
            expect(usage).to_contain_text("剩余 1 次")
            page.goto(base + f"/notes/?id={note}")
            page.get_by_role("button", name="打开 AI 对话").click()
            conversation.get_by_role("button", name="重试回答").click()
            expect(conversation.locator(".conversation-message.assistant")).to_have_count(
                2, timeout=20000
            )
            page.goto(base + "/settings/")
            expect(usage).to_contain_text("已用 2 次")
            field.fill("")
            panel.get_by_role("button", name="保存月度限额").click()
            expect(usage).to_contain_text("当前不限")
            expect(usage).to_contain_text("已用 2 次")
            page.set_viewport_size({"width": 390, "height": 844})
            panel.scroll_into_view_if_needed()
            page.screenshot(path=str(RESULTS / "model-usage-mobile.png"))
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            context.set_offline(True)
            panel.get_by_role("button", name="刷新用量").click()
            expect(panel.get_by_role("alert")).to_be_visible()
            context.set_offline(False)
            panel.get_by_role("button", name="刷新用量").click()
            expect(panel.get_by_role("alert")).to_have_count(0)
            expect(usage).to_contain_text("已用 2 次")
            page.set_viewport_size({"width": 1440, "height": 1000})
            panel.scroll_into_view_if_needed()
            page.screenshot(path=str(RESULTS / "model-usage-desktop.png"))
            assert errors == [], errors
        print(
            "Model usage Chromium passed: settings, persistence, quota, capture, retry, "
            "offline and mobile"
        )


if __name__ == "__main__":
    main()
