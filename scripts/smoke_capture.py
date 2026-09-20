"""Browser acceptance with a temporary database and offline HTML/model fixtures.

Run after `make build`: uv run --no-project --with playwright python scripts/smoke_capture.py
Install Chromium with `uv run --no-project --with playwright playwright install chromium` if needed.
"""

import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="clipo-capture-browser-") as directory:
        temp = Path(directory)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(
            CLIPO_SECRET_KEY=secrets.token_hex(32),
            CLIPO_DATABASE_URL=f"sqlite:///{temp / 'test.db'}",
            CLIPO_QUEUE_PATH=str(temp / "huey.db"),
            CLIPO_BASE_URL=base,
            CLIPO_STATIC_PATH=str(ROOT / "backend/app/static"),
            CLIPO_SMOKE_PORT=str(port),
        )
        # Let the browser configure the fixture model independently of deployment overrides.
        env.pop("CLIPO_LLM_API_KEY", None)
        env.pop("CLIPO_LLM_MODEL", None)
        env.pop("CLIPO_LLM_BASE_URL", None)
        subprocess.run(
            [str(ROOT / ".venv/bin/alembic"), "-c", "backend/alembic.ini", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
        )
        processes = []
        with (temp / "server.log").open("w") as log:
            try:
                for mode in ("api", "worker"):
                    processes.append(
                        subprocess.Popen(
                            [
                                str(ROOT / ".venv/bin/python"),
                                str(ROOT / "backend/tests/browser/server.py"),
                                mode,
                            ],
                            cwd=ROOT,
                            env=env,
                            stdout=log,
                            stderr=log,
                        )
                    )
                for _ in range(100):
                    try:
                        urllib.request.urlopen(base + "/api/v1/health", timeout=1)
                        break
                    except OSError:
                        if any(process.poll() is not None for process in processes):
                            raise RuntimeError((temp / "server.log").read_text()) from None
                        time.sleep(0.1)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(
                        headless=True,
                        executable_path=os.environ.get("CLIPO_TEST_CHROMIUM"),
                    )
                    context = browser.new_context(viewport={"width": 1440, "height": 1000})
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base)
                    page.get_by_label("用户名").fill("smoke-admin")
                    page.get_by_label("邮箱").fill("smoke@example.com")
                    page.get_by_label("密码", exact=True).fill("smoke-password-12345")
                    page.get_by_role("button", name="下一步").click()
                    page.get_by_role("button", name="跳过 AI，创建空间").click()
                    expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
                    page.get_by_label("网页链接").fill("https://example.com/article")
                    page.get_by_role("button", name="保存网页").click()
                    expect(page.locator(".job-status.success")).to_be_visible(timeout=20000)
                    page.get_by_role("link", name="阅读笔记").click()
                    expect(
                        page.get_by_text("未生成摘要：尚未配置模型密钥", exact=False)
                    ).to_be_visible()
                    expect(page.locator(".original-text")).to_contain_text("保留来源")
                    page.screenshot(path=str(temp / "original-note.png"), full_page=True)
                    page.goto(base + "/settings/")
                    page.get_by_label("API Key").fill("offline-test-key")
                    page.get_by_role("button", name="保存配置").click()
                    expect(page.locator(".notice.success")).to_be_visible()
                    page.goto(base + "/")
                    page.get_by_label("网页链接").fill("https://example.com/summary")
                    page.get_by_role("button", name="保存网页").click()
                    expect(page.locator(".job-status.success")).to_have_count(2, timeout=20000)
                    page.get_by_role("link", name="阅读笔记").first.click()
                    expect(page.locator(".key-points")).to_contain_text("定期回顾并付诸行动")
                    expect(page.locator(".markdown h2")).to_have_text("给未来留一份笔记")
                    page.get_by_role("button", name="删除笔记").click()
                    page.get_by_role("button", name="确认删除").click()
                    expect(page.locator(".note-card")).to_have_count(1)
                    page.get_by_label("网页链接").fill("https://example.com/retry")
                    page.get_by_role("button", name="保存网页").click()
                    expect(page.locator(".job-status.failed")).to_be_visible(timeout=20000)
                    page.get_by_role("button", name="重新保存", exact=True).click()
                    expect(page.locator(".job-status.failed")).to_have_count(0)
                    expect(page.locator(".job-status.success")).to_have_count(3, timeout=20000)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.get_by_role("button", name="退出登录").last.click()
                    expect(page.get_by_role("heading", name="欢迎回到 Clipo")).to_be_visible()
                    page.goto(base + "/share/?text=https%3A%2F%2Fexample.com%2Fshared")
                    expect(page.get_by_role("heading", name="欢迎回到 Clipo")).to_be_visible()
                    page.get_by_label("用户名").fill("smoke-admin")
                    page.get_by_label("密码", exact=True).fill("smoke-password-12345")
                    page.get_by_role("button", name="登录你的空间").click()
                    expect(page.get_by_role("heading", name="保存队列.")).to_be_visible()
                    expect(page.locator(".job-status.success")).to_have_count(4, timeout=20000)
                    page.goto(base + "/")
                    expect(page.locator(".note-card")).to_have_count(3)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    screenshots = ROOT / "frontend/test-results"
                    screenshots.mkdir(exist_ok=True)
                    page.screenshot(path=str(screenshots / "notes-mobile.png"), full_page=True)
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.screenshot(path=str(screenshots / "notes-desktop.png"), full_page=True)
                    page.locator(".note-card").first.click()
                    expect(page.locator(".key-points")).to_be_visible()
                    page.screenshot(path=str(screenshots / "note-detail.png"), full_page=True)
                    manifest = context.request.get(base + "/manifest.webmanifest").json()
                    assert manifest["share_target"]["action"] == "/share/"
                    for icon in manifest["icons"]:
                        assert context.request.get(base + icon["src"]).status == 200
                    page.evaluate("navigator.serviceWorker.ready")
                    assert not errors, errors
                    print(
                        json.dumps(
                            {
                                "browser": "Chromium",
                                "flows": [
                                    "setup",
                                    "URL capture",
                                    "original-only note",
                                    "AI summary",
                                    "delete",
                                    "manual retry",
                                    "share through login",
                                    "mobile layout",
                                    "manifest and service worker",
                                ],
                                "console_errors": errors,
                            },
                            ensure_ascii=False,
                        )
                    )
                    browser.close()
            finally:
                for process in processes:
                    process.terminate()
                for process in processes:
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
