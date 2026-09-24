# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""笔记摘要与分享浏览器验收，使用临时实例和固定模型。"""

import os
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from smoke_backup import ACCOUNT, RESULTS, launch, request


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="clipo-notes-smoke-") as temporary,
        ExitStack() as stack,
    ):
        base = launch(stack, Path(temporary) / "instance")
        token = request(base, "/setup", body=ACCOUNT)["access_token"]
        job = request(
            base,
            "/captures",
            token,
            {
                "url": "https://example.com/note",
                "payload": {
                    "title": "笔记能力验收",
                    "text": "保留完整原文，方便之后整理与回顾。",
                    "tags": ["手动标签"],
                    "comments": [
                        {"author": "读者", "content": "每周安排固定时间回顾并采取行动", "likes": 5}
                    ],
                },
            },
        )
        for _ in range(100):
            status = request(base, "/jobs/" + job["job_id"], token)
            if status["status"] == "success":
                break
            time.sleep(0.1)
        assert status["status"] == "success"
        note_id = status["note_id"]
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
            page.get_by_role("button", name="登录你的空间", exact=True).click()
            expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
            page.goto(base + f"/notes/?id={note_id}")
            panel = page.get_by_role("region", name="重新生成摘要", exact=True)
            panel.get_by_role("button", name="重新生成摘要", exact=True).click()
            expect(panel.get_by_role("status")).to_contain_text("摘要生成失败", timeout=20000)
            expect(page.locator(".original-text")).to_contain_text("保留完整原文")
            page.goto(base + "/settings/#llm")
            # Configure through the authenticated API; no real model endpoint is contacted.
            page.evaluate("""async () => {
                const session = await fetch('/api/v1/auth/refresh', {
                    method: 'POST', headers: {'Content-Type':'application/json'}, body:'{}'
                }).then(r => r.json());
                const response = await fetch('/api/v1/settings', {
                    method:'PUT', headers: {'Content-Type':'application/json',
                        Authorization:'Bearer ' + session.access_token},
                    body:JSON.stringify({llm:{api_key:'offline-only',model:'offline'}})
                });
                if (!response.ok) throw new Error('Fixture configuration failed');
            }""")
            page.goto(base + f"/notes/?id={note_id}")
            panel.get_by_role("button", name="重试摘要", exact=True).click()
            expect(panel.get_by_role("status")).to_have_text("摘要已更新", timeout=20000)
            expect(page.locator(".markdown")).to_contain_text("给未来留一份笔记")
            expect(page.get_by_role("button", name="移除标签 手动标签", exact=True)).to_be_visible()
            assert len(request(base, "/notes", token)["items"]) == 1
            detail = request(base, f"/notes/{note_id}", token)
            assert detail["comments"][0]["ai_score"] == 0.9
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(RESULTS / "notes-summary-mobile.png"), full_page=True)
            response = context.request.put(
                base + "/api/v1/settings",
                headers={"Authorization": "Bearer " + token},
                data={"llm": {"model": "offline-hostile"}},
            )
            assert response.status == 200
            panel.get_by_role("button", name="重新生成摘要", exact=True).click()
            expect(page.locator(".markdown")).to_contain_text("安全测试", timeout=20000)
            sharing = page.get_by_role("region", name="公开分享", exact=True)
            sharing.locator("summary").click()
            sharing.get_by_role("button", name="确认内容可公开并创建链接").click()
            expect(sharing.get_by_label("分享链接（仅本次显示）")).to_be_visible()
            share_url = sharing.get_by_label("分享链接（仅本次显示）").input_value()
            assert "/public/#" in share_url
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            public_context = browser.new_context(viewport={"width": 390, "height": 844})
            public_page = public_context.new_page()
            external: list[str] = []
            public_page.on(
                "request",
                lambda req: external.append(req.url) if not req.url.startswith(base) else None,
            )
            public_page.on("pageerror", lambda error: errors.append(str(error)))
            public_response = public_page.goto(share_url)
            assert public_response.headers["cache-control"] == "no-store"
            expect(public_page.get_by_role("heading", name="笔记能力验收")).to_be_visible()
            expect(public_page.locator(".markdown")).to_contain_text("给未来留一份笔记")
            expect(public_page.locator(".comment")).to_contain_text("AI 评分 0.9")
            expect(public_page.locator(".markdown")).to_contain_text("安全测试")
            assert public_page.evaluate("window.clipoXss") is None
            assert (
                public_page.locator(
                    "article script, article img, article [onerror], article a[href^='javascript:']"
                ).count()
                == 0
            )
            assert not external, external
            assert public_page.locator("a[target='_blank']").evaluate_all(
                "links => links.every(link => link.rel.includes('noreferrer'))"
            )
            assert (
                public_page.locator("meta[name=robots]")
                .get_attribute("content")
                .startswith("noindex")
            )
            assert public_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert public_page.evaluate("localStorage.length") == 0
            assert public_page.evaluate("async () => (await indexedDB.databases()).length") == 0
            public_page.screenshot(path=str(RESULTS / "notes-public-mobile.png"), full_page=True)
            public_context.set_offline(True)
            expect(public_page.get_by_role("heading", name="笔记能力验收")).to_have_count(0)
            public_context.set_offline(False)
            public_page.goto(share_url)
            expect(public_page.get_by_role("heading", name="笔记能力验收")).to_be_visible()
            sharing.get_by_role("button", name="撤销链接", exact=True).click()
            expect(sharing.get_by_role("status")).to_have_text("分享链接已撤销。")
            public_page.reload()
            expect(public_page.locator("main").get_by_role("alert")).to_contain_text("分享链接无效")
            expect(public_page.get_by_role("heading", name="笔记能力验收")).to_have_count(0)
            public_context.close()
            assert not errors, errors
        print(
            "笔记浏览器验收通过：摘要失败/重试、同篇更新、评论评分、匿名分享/撤销、无离线内容及手机布局"
        )


if __name__ == "__main__":
    main()
