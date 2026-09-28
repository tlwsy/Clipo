# SPDX-License-Identifier: AGPL-3.0-or-later
"""临时实例验收导航请求、分页/筛选恢复及慢网返回位置，不访问真实平台。"""

import json
import os
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright
from smoke_backup import ACCOUNT, RESULTS, launch, request


def check_return(page: Page, toolbar: bool) -> float:
    card = page.locator(".note-card").nth(28)
    card.scroll_into_view_if_needed()
    position = page.evaluate("window.scrollY")
    assert position > 500
    title = card.locator("h2").inner_text()
    card.click()
    expect(page.locator(".reader h1")).to_have_text(title)
    expect(page.locator(".reader-meta")).to_contain_text("小黑盒")
    started = time.monotonic()
    if toolbar:
        page.locator(".reader-toolbar").get_by_role("link", name="全部笔记").click()
    else:
        page.go_back()
    expect(page.locator(".note-card")).to_have_count(30, timeout=450)
    page.wait_for_function(
        "position => Math.abs(scrollY - position) < 5", arg=position, timeout=450
    )
    elapsed = time.monotonic() - started
    expect(page.get_by_label("搜索笔记")).to_have_value("导航验收")
    # The delayed background refresh must also retain all loaded pages and the position.
    page.wait_for_timeout(1300)
    expect(page.locator(".note-card")).to_have_count(30)
    assert abs(page.evaluate("scrollY") - position) < 5
    return elapsed


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipo-navigation-") as temporary, ExitStack() as stack:
        base = launch(stack, Path(temporary) / "instance")
        token = request(base, "/setup", body=ACCOUNT)["access_token"]
        jobs = [
            request(
                base,
                "/captures",
                token,
                {
                    "url": (
                        "https://api.xiaoheihe.cn/v3/bbs/app/api/web/share?link_id=123"
                        if index == 1
                        else f"https://example.com/navigation/{index}"
                    ),
                    "payload": {
                        "title": f"导航验收 {index:02}",
                        "site_name": "知识站" if index == 0 else None,
                        "text": "用于验收浏览器列表分页、筛选和返回位置的离线内容。" * 5,
                        "tags": ["导航"],
                    },
                },
            )
            for index in range(30)
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
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            errors: list[str] = []
            requests: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda req: requests.append(req.url.removeprefix(base)))
            page.goto(base + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间").click()
            expect(page.locator(".note-card")).to_have_count(24)
            page.get_by_label("搜索笔记").fill("导航验收")
            page.get_by_role("button", name="搜索", exact=True).click()
            tag_id = page.get_by_label("按标签筛选").locator("option").nth(1).get_attribute("value")
            page.get_by_label("按标签筛选").select_option(tag_id)
            page.get_by_role("button", name="加载更多").click()
            expect(page.locator(".note-card")).to_have_count(30)
            for title, name in [
                ("导航验收 00", "知识站"),
                ("导航验收 01", "小黑盒"),
                ("导航验收 02", "example.com"),
            ]:
                expect(
                    page.locator(".note-card")
                    .filter(has_text=title)
                    .locator(".note-card-meta span")
                    .first
                ).to_have_text(name)
            expect(page.locator(".offline-status")).to_contain_text("离线可读 30", timeout=20000)
            before_auth = requests.count("/api/v1/auth/me")
            before_prefetch = requests.count("/api/v1/notes?limit=50")

            network = context.new_cdp_session(page)
            network.send("Network.enable")
            network.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 600,
                    "downloadThroughput": -1,
                    "uploadThroughput": -1,
                },
            )
            timings = [check_return(page, toolbar=False), check_return(page, toolbar=True)]
            expect(page.get_by_label("按标签筛选")).to_have_value(tag_id)
            page.screenshot(path=str(RESULTS / "navigation-return-mobile.png"))
            network.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 0,
                    "downloadThroughput": -1,
                    "uploadThroughput": -1,
                },
            )
            for name, heading in [("设置", "空间设置."), ("保存队列", "保存队列.")]:
                page.get_by_role("navigation", name="主导航").get_by_role("link", name=name).click()
                expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
            page.get_by_role("navigation", name="主导航").get_by_role(
                "link", name="全部笔记"
            ).click()
            expect(page.locator(".note-card")).to_have_count(30)
            assert requests.count("/api/v1/auth/me") == before_auth
            assert requests.count("/api/v1/notes?limit=50") == before_prefetch
            page.get_by_role("button", name="退出登录").last.click()
            expect(page.get_by_role("heading", name="欢迎回到 Clipo")).to_be_visible()
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间").click()
            expect(page.get_by_label("搜索笔记")).to_have_value("")
            expect(page.locator(".note-card")).to_have_count(24)
            assert not errors, errors
            print(
                json.dumps(
                    {
                        "return_ms": [round(value * 1000) for value in timings],
                        "extra_auth_requests": 0,
                        "extra_prefetch_batches": 0,
                        "console_errors": errors,
                    }
                )
            )


if __name__ == "__main__":
    main()
