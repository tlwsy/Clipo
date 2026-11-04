# SPDX-License-Identifier: AGPL-3.0-or-later
"""在与原生 App 相同的 M1 夹具上核对网页阅读语义，由 smoke_mobile.py --web 调用。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    base = sys.argv[1]
    assert urlsplit(base).hostname == "127.0.0.1"
    output = Path(__file__).resolve().parents[1] / "mobile/test-results/web-m1"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get("CLIPO_TEST_CHROMIUM"))
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route(
                "**/*",
                lambda route: (
                    route.continue_() if route.request.url.startswith(base) else route.abort()
                ),
            )
            page.goto(base + "/login/")
            page.get_by_label("用户名").fill("mobile-test")
            page.get_by_label("密码", exact=True).fill("mobile-test-password")
            page.get_by_role("button", name="登录你的空间", exact=True).click()
            page.locator(".note-card-link").filter(has_text="Mobile acceptance").click()
            expect(page.get_by_role("heading", name="Rich heading", exact=True)).to_be_visible()
            expect(page.get_by_text("Bold sample", exact=True)).to_have_css("font-weight", "700")
            expect(page.get_by_role("cell", name="Column B", exact=True)).to_be_visible()
            page.get_by_text("More details", exact=True).click()
            expect(page.get_by_text("Hidden paragraph", exact=True)).to_be_visible()
            expect(page.locator('[data-annotation-block="0"]')).to_contain_text("中文😀内容")
            assert (
                page.locator('[data-annotation-block="0"]').evaluate(
                    "el => el.textContent.slice(0, 4)"
                )
                == "中文😀"
            )
            page.screenshot(path=str(output / "reader-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(output / "reader-phone.png"), full_page=True)
            assert not errors, errors
            print("M1 网页/原生共用夹具语义检查通过；截图：" + str(output))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
