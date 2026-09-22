# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""验收已有的空测试 Compose，默认 58000 端口；拒绝已初始化的实例。"""

import argparse
import io
import json
import os
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import expect, sync_playwright
from smoke_backup import request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:58000")
    base = parser.parse_args().base_url.rstrip("/")
    assert request(base, "/meta/version")["setup_completed"] is False, "只允许空测试实例"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("CLIPO_TEST_CHROMIUM"), headless=True
        )
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            page.get_by_label("用户名").fill("compose-test")
            page.get_by_label("邮箱").fill("compose@example.com")
            page.get_by_label("密码", exact=True).fill("compose-test-password-123")
            page.get_by_role("button", name="下一步").click()
            with page.expect_response(
                lambda response: response.url.endswith("/api/v1/setup")
                and response.request.method == "POST"
            ) as setup:
                page.get_by_role("button", name="跳过 AI，创建空间").click()
            assert setup.value.status == 201
            token = setup.value.json()["access_token"]
            expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
            job = request(
                base,
                "/captures",
                token,
                {
                    "url": "https://example.com/compose-check",
                    "payload": {
                        "title": "容器部署验收",
                        "text": "容器中的后台任务完整保存中文笔记。",
                        "tags": ["部署"],
                        "comments": [{"content": "这是一条离线验收评论", "likes": 3}],
                    },
                },
            )
            for _ in range(100):
                current = request(base, "/jobs/" + job["job_id"], token)
                if current["status"] == "success":
                    break
                time.sleep(0.2)
            assert current["status"] == "success"
            page.reload()
            expect(page.locator(".note-card")).to_have_count(1)
            page.locator(".note-card").click()
            expect(page.locator(".original-text")).to_contain_text("中文笔记")
            expect(page.get_by_text("未生成摘要", exact=False).first).to_be_visible()
            assert len(request(base, "/notes?q=" + quote("中文"), token)["items"]) == 1
            page.goto(base + "/settings/#backups")
            panel = page.locator("#backups")
            panel.get_by_role("button", name="导出 JSON 与 Markdown").click()
            expect(panel.get_by_text("导出 · 已完成", exact=True)).to_be_visible(timeout=20000)
            with page.expect_download() as download:
                panel.get_by_role("button", name="下载 ZIP").first.click()
            with zipfile.ZipFile(io.BytesIO(Path(download.value.path()).read_bytes())) as archive:
                saved = json.loads(archive.read("library.json"))
                assert saved["notes"][0]["comments"][0]["likes"] == 3
            with urllib.request.urlopen(base + "/api/v1/health", timeout=5) as health:
                assert health.status == 200
            assert not errors, errors
            print(
                "空 Compose 浏览器验收通过：设置向导、内容直传、worker 落库、"
                "摘要降级、中文搜索、备份下载"
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
