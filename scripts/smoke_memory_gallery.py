# SPDX-License-Identifier: AGPL-3.0-or-later
"""回忆卡片、阅读时长与离线；临时实例、真实 API/worker 和离线模型。"""

import json
import os
import sqlite3
import tempfile
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright
from smoke_annotations import wait_job
from smoke_backup import ACCOUNT, RESULTS, launch, request


def current_id(page: Page) -> int:
    href = page.get_by_role("link", name="打开阅读").get_attribute("href")
    assert href
    return int(href.split("id=")[1])


def swipe(page: Page, dx: int, dy: int = 0) -> None:
    session = page.context.new_cdp_session(page)
    try:
        session.send(
            "Input.dispatchTouchEvent",
            {
                "type": "touchStart",
                "touchPoints": [{"x": 190, "y": 300}],
            },
        )
        for step in range(1, 6):
            session.send(
                "Input.dispatchTouchEvent",
                {
                    "type": "touchMove",
                    "touchPoints": [{"x": 190 + dx * step / 5, "y": 300 + dy * step / 5}],
                },
            )
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    finally:
        session.detach()


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipo-memory-") as temporary, ExitStack() as stack:
        directory = Path(temporary) / "instance"
        base = launch(stack, directory)
        token = request(
            base,
            "/setup",
            body={
                **ACCOUNT,
                "llm": {"api_key": "offline-only", "model": "offline-default"},
            },
        )["access_token"]
        ids = []
        for index, title in enumerate(
            (
                "重拾深度工作的节奏",
                "给未来留一份笔记",
                "慢慢收集，让灵感生长",
                "把阅读变成下一次行动",
            )
        ):
            ids.append(
                wait_job(
                    base,
                    token,
                    request(
                        base,
                        "/captures",
                        token,
                        {
                            "url": f"https://example.com/memory/{index}",
                            "payload": {
                                "title": title,
                                "text": "保存阅读中有用的观点，保留出处，并把它变成下一次行动。"
                                * 20,
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
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, has_touch=True)
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间").click()
            expect(page.locator(".note-card")).to_have_count(4)
            expect(page.locator(".offline-status")).to_contain_text("离线可读 4", timeout=20000)
            with sqlite3.connect(directory / "test.db") as db:
                assert (
                    db.execute(
                        "SELECT count(*) FROM notes WHERE last_viewed_at IS NOT NULL"
                    ).fetchone()[0]
                    == 0
                )
            page.get_by_role("link", name="回忆", exact=True).click()
            expect(page.get_by_role("dialog", name="回忆")).to_be_visible()
            expect(page.locator(".memory-progress")).to_have_text("1 / 4")
            first = current_id(page)
            page.screenshot(path=str(RESULTS / "memory-desktop.png"))
            page.get_by_role("button", name="☆ 收藏", exact=True).click()
            expect(page.get_by_role("button", name="★ 已收藏", exact=True)).to_have_attribute(
                "aria-pressed", "true"
            )
            assert request(base, f"/notes/{first}", token)["is_favorite"]
            page.keyboard.press("ArrowRight")
            expect(page.locator(".memory-progress")).to_have_text("2 / 4")
            page.keyboard.press("ArrowLeft")
            expect(page.locator(".memory-progress")).to_have_text("1 / 4")
            assert current_id(page) == first
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.locator(".memory-dialog").evaluate("e => e.scrollWidth <= e.clientWidth")
            page.screenshot(path=str(RESULTS / "memory-mobile.png"))
            swipe(page, 20, 120)
            expect(page.locator(".memory-progress")).to_have_text("1 / 4")
            swipe(page, -100)
            expect(page.locator(".memory-progress")).to_have_text("2 / 4")
            second = current_id(page)
            swipe(page, 100)
            expect(page.locator(".memory-progress")).to_have_text("3 / 4")
            assert request(base, f"/notes/{second}", token)["is_favorite"]
            removed = current_id(page)
            page.route(
                "**/api/v1/memory-gallery/dismiss",
                lambda route: route.fulfill(
                    status=503,
                    content_type="application/json",
                    body=json.dumps({"error": {"code": "unavailable", "message": "测试暂不可用"}}),
                ),
            )
            page.get_by_role("button", name="30 天内不再推荐").click()
            expect(page.locator(".memory-dialog").get_by_role("alert")).to_contain_text(
                "测试暂不可用"
            )
            assert current_id(page) == removed
            page.unroute("**/api/v1/memory-gallery/dismiss")
            page.get_by_role("button", name="30 天内不再推荐").click()
            expect(page.get_by_text("已从回忆移除", exact=False)).to_be_visible()
            assert removed not in {
                row["id"] for row in request(base, "/memory-gallery", token)["notes"]
            }
            assert request(base, f"/notes/{removed}", token)["id"] == removed
            opened = current_id(page)
            page.get_by_role("link", name="打开阅读").click()
            expect(page.locator(".reader h1")).to_be_visible()
            page.bring_to_front()
            page.wait_for_timeout(1400)
            page.get_by_role("link", name="回忆", exact=True).click()
            expect(page.locator(".memory-progress")).to_have_text("1 / 2")
            with sqlite3.connect(directory / "test.db") as db:
                duration, viewed = db.execute(
                    "SELECT reading_duration_seconds,last_viewed_at FROM notes WHERE id=?",
                    (opened,),
                ).fetchone()
                assert 1 <= duration <= 10 and viewed, (duration, viewed)
            remaining = request(base, "/memory-gallery", token)["notes"]
            assert {row["id"] for row in remaining} == set(ids) - {removed, opened}
            page.get_by_role("button", name="跳过", exact=True).click()
            page.get_by_role("button", name="跳过", exact=True).click()
            expect(page.get_by_role("heading", name="已浏览全部")).to_be_visible()
            page.get_by_role("button", name="再来一组").click()
            expect(page.locator(".memory-progress")).to_have_text("1 / 2")
            # Escape closes the native modal and returns to the existing list.
            page.keyboard.press("Escape")
            expect(page.get_by_role("dialog")).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            for _ in range(2):
                page.get_by_role("link", name="回忆", exact=True).click()
                expect(page.locator(".memory-card")).to_be_visible()
                page.get_by_role("button", name="30 天内不再推荐").click()
                page.get_by_role("button", name="关闭", exact=True).click()
            page.get_by_role("link", name="回忆", exact=True).click()
            expect(page.get_by_role("heading", name="暂时没有适合重访的笔记")).to_be_visible()
            page.get_by_role("button", name="关闭", exact=True).click()
            context.set_offline(True)
            page.get_by_role("link", name="回忆", exact=True).click()
            expect(page.locator(".memory-dialog").get_by_role("alert")).to_contain_text(
                "回忆需要联网"
            )
            context.set_offline(False)
            page.get_by_role("button", name="重新加载").click()
            expect(page.get_by_role("heading", name="暂时没有适合重访的笔记")).to_be_visible()
            assert not errors, errors
            print(
                "回忆筛选、收藏、键盘/触摸、移除失败/持久化、实际阅读上报、预加载隔离、空状态、离线恢复与手机布局通过"
            )


if __name__ == "__main__":
    main()
