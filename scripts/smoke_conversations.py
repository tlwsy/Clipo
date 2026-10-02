# SPDX-License-Identifier: AGPL-3.0-or-later
"""私人对话的真实 API/worker、浏览器恢复与 Markdown 安全验收；仅离线模型。"""

import os
import sqlite3
import tempfile
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Route, expect, sync_playwright
from smoke_annotations import wait_job
from smoke_backup import ACCOUNT, RESULTS, launch, request


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipo-chat-") as temporary, ExitStack() as stack:
        directory = Path(temporary) / "instance"
        base = launch(stack, directory)
        token = request(
            base,
            "/setup",
            body={**ACCOUNT, "llm": {"api_key": "offline-only", "model": "offline-default"}},
        )["access_token"]
        note_id = wait_job(
            base,
            token,
            request(
                base,
                "/captures",
                token,
                {
                    "url": "https://example.com/conversation",
                    "payload": {
                        "title": "让阅读成为下一次行动",
                        "text": "保存阅读中有用的观点，保留出处，并定期回顾，把它变成下一次行动。",
                    },
                },
            ),
        )
        path = f"/notes/{note_id}/conversations"
        with sync_playwright() as pw, ExitStack() as browsers:
            browser = pw.chromium.launch(
                headless=True, executable_path=os.environ.get("CLIPO_TEST_CHROMIUM")
            )
            browsers.callback(browser.close)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            errors: list[str] = []
            requests: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda item: requests.append(item.url))
            page.goto(base + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间").click()
            expect(page.locator(".note-card")).to_have_count(1)
            page.goto(base + f"/notes/?id={note_id}")
            page.get_by_role("button", name="打开 AI 对话").click()
            panel = page.get_by_role("region", name="私人 AI 对话")
            expect(panel.get_by_text("还没有对话。", exact=False)).to_be_visible()
            page.get_by_label("向 AI 提问").fill("这篇文章的主要论点是什么？")
            page.get_by_role("button", name="发送问题").click()
            expect(panel.locator(".conversation-message.assistant")).to_have_count(1, timeout=20000)
            expect(panel.locator(".conversation-message.assistant strong").last).to_have_text(
                "保留出处，并定期回顾"
            )
            page.get_by_label("向 AI 提问").fill("把上面的建议变成一个行动步骤")
            page.get_by_role("button", name="发送问题").click()
            expect(panel.locator(".conversation-message.assistant")).to_have_count(2, timeout=20000)
            expect(panel.get_by_text("延续上轮回答：", exact=False)).to_be_visible()
            page.reload()
            page.get_by_role("button", name="打开 AI 对话").click()
            expect(panel.locator(".conversation-message")).to_have_count(4)
            # Reader updates must preserve component identity and the open dialogue.
            page.get_by_role("button", name="阅读样式", exact=True).click()
            style = page.get_by_role("dialog", name="阅读样式")
            style.get_by_role("button", name="紧凑", exact=True).click()
            style.get_by_role("button", name="保存样式").click()
            expect(style).to_have_count(0)
            expect(panel.locator(".conversation-message")).to_have_count(4)
            page.screenshot(path=str(RESULTS / "conversations-desktop.png"), full_page=True)

            # Missing credentials fail without losing the question; retry uses newly saved settings.
            response = page.request.put(
                base + "/api/v1/settings",
                headers={"Authorization": "Bearer " + token},
                data={"llm": {"api_key": ""}},
            )
            assert response.ok
            page.get_by_label("向 AI 提问").fill("保留这个失败问题")
            page.get_by_role("button", name="发送问题").click()
            expect(panel.get_by_role("button", name="重试回答")).to_be_visible(timeout=20000)
            expect(panel.get_by_text("尚未配置模型密钥", exact=False)).to_be_visible()
            response = page.request.put(
                base + "/api/v1/settings",
                headers={"Authorization": "Bearer " + token},
                data={"llm": {"api_key": "offline-only", "model": "offline-hostile"}},
            )
            assert response.ok
            panel.get_by_role("button", name="重试回答").click()
            expect(panel.locator(".conversation-message.assistant")).to_have_count(3, timeout=20000)
            assert panel.locator("img, script, a[href^='javascript:']").count() == 0
            assert not page.evaluate("window.clipoXss")
            assert not any("chat-track" in url for url in requests)

            # Lose only the first POST response, then send the same question again.
            posted: list[dict] = []

            def drop_response(route: Route) -> None:
                if route.request.method != "POST":
                    route.continue_()
                    return
                posted.append(route.request.post_data_json)
                if len(posted) == 1:
                    result = route.fetch()
                    assert result.status == 202
                    route.abort("failed")
                else:
                    route.continue_()

            page.route(base + "/api/v1" + path, drop_response)
            page.get_by_label("向 AI 提问").fill("丢失响应也只保存一次")
            page.get_by_role("button", name="发送问题").click()
            expect(panel.get_by_role("alert")).to_contain_text("无法连接服务")
            expect(page.get_by_label("向 AI 提问")).to_have_value("丢失响应也只保存一次")
            page.get_by_role("button", name="发送问题").click()
            expect(panel.locator(".conversation-message.assistant")).to_have_count(4, timeout=20000)
            assert len(posted) == 2 and posted[0] == posted[1]
            page.unroute(base + "/api/v1" + path, drop_response)
            assert len(request(base, path, token)["turns"]) == 8

            # Seed a longer private history to exercise cursor pagination in the browser.
            with sqlite3.connect(directory / "test.db") as db:
                for index in range(4, 25):
                    for role in ("user", "assistant"):
                        db.execute(
                            "INSERT INTO note_conversations "
                            "(id,user_id,note_id,turn_index,role,content,created_at) "
                            "VALUES (?,1,?,?,?,?,?)",
                            (
                                uuid.uuid4().hex,
                                note_id,
                                index,
                                role,
                                f"历史{index}：{role}",
                                datetime.now(UTC).isoformat(),
                            ),
                        )
            page.get_by_role("button", name="收起对话").click()
            page.get_by_role("button", name="打开 AI 对话").click()
            expect(panel.locator(".conversation-message")).to_have_count(40)
            page.get_by_role("button", name="查看更早对话").click()
            expect(panel.locator(".conversation-message")).to_have_count(50)
            expect(page.get_by_role("button", name="查看更早对话")).to_have_count(0)
            context.set_offline(True)
            expect(panel.get_by_text("对话需要联网", exact=False)).to_be_visible()
            page.get_by_label("向 AI 提问").fill("联网后再发送")
            expect(page.get_by_role("button", name="发送问题")).to_be_disabled()
            context.set_offline(False)
            expect(page.get_by_role("button", name="发送问题")).to_be_enabled()
            page.set_viewport_size({"width": 390, "height": 844})
            panel.scroll_into_view_if_needed()
            page.screenshot(path=str(RESULTS / "conversations-mobile.png"))
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            # Closing unmounts the poller and keeps the reader usable.
            page.get_by_role("button", name="收起对话").click()
            expect(page.locator("#note-conversation-panel")).to_have_count(0)
            assert errors == [], errors
        print(
            "Conversations Chromium passed: context, persistence, retry, uncertain POST, "
            "pagination, safe Markdown, offline and mobile"
        )


if __name__ == "__main__":
    main()
