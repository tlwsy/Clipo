"""Load the actual unpacked extension with native permission/action gestures.

Requires Xvfb and python-xlib on Linux. Uses an isolated browser, DB and offline pages.
uv run --no-project --with playwright --with python-xlib python scripts/smoke_extension.py
"""

import base64
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, expect, sync_playwright
from Xlib import XK, X, display
from Xlib.ext import xtest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "backend/tests/fixtures"


def native_keys(keys: list[str]) -> None:
    connection = display.Display()
    for name in keys:
        xtest.fake_input(
            connection, X.KeyPress, connection.keysym_to_keycode(XK.string_to_keysym(name))
        )
    for name in reversed(keys):
        xtest.fake_input(
            connection, X.KeyRelease, connection.keysym_to_keycode(XK.string_to_keysym(name))
        )
    connection.sync()
    connection.close()


def api(
    base: str, path: str, token: str = "", body: dict | None = None, method: str = "GET"
) -> Any:
    request = urllib.request.Request(
        base + "/api/v1" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": "Bearer " + token} if token else {}),
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response) if response.status != 204 else None


def native_click(x: int, y: int) -> None:
    connection = display.Display()
    xtest.fake_input(connection, X.MotionNotify, x=x, y=y)
    xtest.fake_input(connection, X.ButtonPress, 1)
    xtest.fake_input(connection, X.ButtonRelease, 1)
    connection.sync()
    connection.close()


class Popup:
    """Native extension popups are CDP page targets omitted by Playwright page events."""

    def __init__(self, page: Page, session: Any, target: str) -> None:
        self.page = page
        self.session = session
        self.target = target
        self.sequence = 0
        self.responses: dict[int, dict] = {}
        self.attached = session.send("Target.attachToTarget", {"targetId": target})["sessionId"]
        session.on("Target.receivedMessageFromTarget", self.receive)

    def receive(self, event: dict) -> None:
        if event["sessionId"] == self.attached:
            message = json.loads(event["message"])
            if "id" in message:
                self.responses[message["id"]] = message

    def command(self, method: str, params: dict) -> dict:
        self.sequence += 1
        identifier = self.sequence
        self.session.send(
            "Target.sendMessageToTarget",
            {
                "sessionId": self.attached,
                "message": json.dumps({"id": identifier, "method": method, "params": params}),
            },
        )
        for _ in range(200):
            if identifier in self.responses:
                response = self.responses.pop(identifier)
                assert "error" not in response, response
                return response["result"]
            self.page.wait_for_timeout(50)
        raise AssertionError("Native popup did not respond")

    def evaluate(self, expression: str) -> Any:
        result = self.command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        assert "exceptionDetails" not in result, result
        return result["result"].get("value")

    def fill(self, selector: str, value: str) -> None:
        self.evaluate(f"document.querySelector({json.dumps(selector)}).value={json.dumps(value)}")

    def click(self, selector: str) -> None:
        self.evaluate(f"document.querySelector({json.dumps(selector)}).click()")

    def wait_status(self, expected: str) -> None:
        message = ""
        for _ in range(120):
            message = self.evaluate("document.querySelector('#result').textContent")
            if expected in message:
                return
            self.page.wait_for_timeout(200)
        raise AssertionError(f"Popup expected {expected}, got {message}")

    def screenshot(self, path: Path) -> None:
        result = self.command("Page.captureScreenshot", {"format": "png"})
        path.write_bytes(base64.b64decode(result["data"]))

    def close(self) -> None:
        self.session.send("Target.closeTarget", {"targetId": self.target})
        self.session.detach()


def open_popup(context: BrowserContext, page: Page) -> Popup:
    page.bring_to_front()
    native_click(1185, 72)
    page.wait_for_timeout(300)
    native_click(994, 232)
    session = context.new_cdp_session(page)
    for _ in range(40):
        targets = session.send("Target.getTargets")["targetInfos"]
        target = next((item for item in targets if item["url"].endswith("/popup/index.html")), None)
        if target:
            popup = Popup(page, session, target["targetId"])
            page.wait_for_timeout(300)
            return popup
        page.wait_for_timeout(100)
    raise AssertionError("Extension action did not open its native popup")


def wait_note(base: str, auth: str, title: str) -> dict:
    for _ in range(100):
        notes = api(base, "/notes", auth)["items"]
        found = next((note for note in notes if note["title"] == title), None)
        if found:
            return api(base, f"/notes/{found['id']}", auth)
        time.sleep(0.2)
    raise AssertionError("Expected extension note did not finish")


def check_browser(base: str, auth: str, token: dict, temp: Path) -> None:
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(temp / "browser"),
            executable_path=os.environ.get("CLIPO_TEST_CHROMIUM"),
            headless=False,
            args=[
                f"--disable-extensions-except={ROOT / 'extension'}",
                f"--load-extension={ROOT / 'extension'}",
                "--window-size=1280,900",
            ],
        )
        try:
            worker = (
                context.service_workers[0]
                if context.service_workers
                else context.wait_for_event("serviceworker")
            )
            origin = worker.url.split("/background/")[0]
            assert worker.evaluate("chrome.permissions.getAll()")["origins"] == []
            errors = []
            context.on(
                "page", lambda page: page.on("pageerror", lambda error: errors.append(str(error)))
            )
            for host, filename in [
                ("example.com", "extension-generic.html"),
                ("www.xiaohongshu.com", "extension-xiaohongshu.html"),
                ("www.xiaoheihe.cn", "extension-xiaoheihe.html"),
            ]:
                content = (FIXTURES / filename).read_text()
                context.route(
                    f"https://{host}/**",
                    lambda route, request, body=content: route.fulfill(
                        content_type="text/html", body=body
                    ),
                )
            context.route("https://images.example.com/**", lambda route: route.fulfill(status=204))
            options = context.new_page()
            options.goto(origin + "/options/index.html")
            options.get_by_label("服务器地址").fill(base)
            options.get_by_label("API Token").fill(token["token"])
            options.get_by_role("button", name="保存配置", exact=True).click()
            # Chrome's native host permission prompt defaults to Cancel; Tab selects Allow.
            options.wait_for_timeout(500)
            native_keys(["Tab"])
            native_keys(["Return"])
            expect(options.get_by_role("status")).to_have_text("配置已保存，连接正常。")
            assert worker.evaluate("chrome.permissions.getAll()")["origins"] == [
                "http://127.0.0.1/*"
            ]
            options.get_by_role("button", name="测试连接").click()
            expect(options.get_by_role("status")).to_contain_text("连接成功")
            screenshots = ROOT / "frontend/test-results"
            screenshots.mkdir(exist_ok=True)
            # Clear the credential field before screenshotting the settings UI.
            options.get_by_label("API Token").fill("")
            options.screenshot(path=str(screenshots / "extension-options.png"))
            page = context.new_page()
            page.goto("https://example.com/article")
            page.evaluate("""() => {
                    const range=document.createRange();
                    range.selectNodeContents(document.querySelector('#selected'));
                    const selected=getSelection();
                    selected.removeAllRanges(); selected.addRange(range);
                }""")
            popup = open_popup(context, page)
            popup.fill("#tags", "浏览器, 测试")
            popup.click("#capture")
            popup.wait_status("笔记已保存")
            popup.screenshot(screenshots / "extension-popup.png")
            popup.close()
            note = wait_note(base, auth, "普通网页验收")
            assert note["content"]["selection"] == "选区文字另行保留。"
            assert "DO_NOT_CAPTURE" not in note["content"]["text"]
            assert "不要保存导航" not in note["content"]["text"]
            assert sorted(tag["name"] for tag in note["tags"]) == ["测试", "浏览器"]
            assert note["status"] == "original_only"
            for url, title, count in [
                ("https://www.xiaohongshu.com/explore/fixture123", "平台 DOM 直取验收", 12),
                ("https://www.xiaoheihe.cn/app/bbs/link/fixture", "小黑盒 DOM 验收", 2),
            ]:
                page.goto(url)
                popup = open_popup(context, page)
                popup.click("#capture")
                popup.wait_status("笔记已保存")
                popup.close()
                note = wait_note(base, auth, title)
                assert len(note["comments"]) == count
                assert note["content"]["images"]
                assert "不采集楼中楼" not in json.dumps(note, ensure_ascii=False)
                if count == 12:
                    assert note["comments"][0]["likes"] == 12000
                    assert note["content"]["capture_warnings"] == []
            # Boundaries: disabled comments, cap warning, unknown/login DOM, missing metadata.
            extract = (ROOT / "extension/content/extract.mjs").read_text().replace("export ", "", 1)
            page.goto("https://www.xiaohongshu.com/explore/fixture123")
            disabled = page.evaluate("async () => {" + extract + "; return await collectPage(0); }")
            assert disabled["payload"]["comments"] == []
            limited = page.evaluate("async () => {" + extract + "; return await collectPage(1); }")
            assert len(limited["payload"]["comments"]) == 1
            assert limited["payload"]["capture_warnings"]
            page.evaluate("document.querySelector('.note-container').remove()")
            invalid = page.evaluate("async () => {" + extract + "; return await collectPage(); }")
            assert "error" in invalid
            # The native page context-menu grants activeTab independently of popup.
            page.goto("https://example.com/context")
            page.evaluate("document.title='右键菜单验收'")
            page.locator("h1").click(button="right")
            native_keys(["End"])
            native_keys(["Up"])
            native_keys(["Up"])
            native_keys(["Return"])
            assert wait_note(base, auth, "右键菜单验收")["content"]["text"]
            # Real large request travels through every upload endpoint, after closing popup.
            page.goto("https://example.com/large")
            page.evaluate("""() => {
                document.title = '大正文分块验收';
                document.querySelector('article').textContent = '正文'.repeat(950000);
            }""")
            popup = open_popup(context, page)
            popup.click("#capture")
            popup.close()
            large = wait_note(base, auth, "大正文分块验收")
            assert len(large["content"]["text"]) == 1900000
            assert api(base, "/jobs", auth)["items"][0]["status"] == "success"
            # Fail a submission after extraction, stop the actual extension worker, then resume.
            worker.evaluate("""() => {
                const original = fetch;
                self.fetch = (input, options) => String(input).endsWith('/captures')
                    ? Promise.reject(new TypeError('offline test')) : original(input, options);
            }""")
            page.goto("https://example.com/resume")
            page.evaluate("document.title='中断恢复验收'")
            popup = open_popup(context, page)
            popup.click("#capture")
            popup.wait_status("连接失败")
            assert popup.evaluate(
                "document.querySelector('#pending-count').textContent"
            ).startswith("1")
            popup.close()
            session = context.new_cdp_session(page)
            versions = []
            session.on(
                "ServiceWorker.workerVersionUpdated",
                lambda event: versions.extend(event["versions"]),
            )
            session.send("ServiceWorker.enable")
            page.wait_for_timeout(500)
            version = next(
                item for item in reversed(versions) if item["scriptURL"].startswith(origin)
            )
            session.send("ServiceWorker.stopWorker", {"versionId": version["versionId"]})
            session.detach()
            popup = open_popup(context, page)
            popup.click("#resume")
            popup.wait_status("笔记已保存")
            popup.close()
            assert wait_note(base, auth, "中断恢复验收")["content"]["text"]
            assert (
                sum(note["title"] == "中断恢复验收" for note in api(base, "/notes", auth)["items"])
                == 1
            )
            # API Token revocation is surfaced without exposing token/server response bodies.
            api(base, f"/tokens/{token['id']}", auth, method="DELETE")
            popup = open_popup(context, page)
            popup.click("#capture")
            popup.wait_status("API Token 已失效")
            popup.close()
            assert (
                api(base, "/settings", auth)["platform_cookies"]["xiaohongshu"]["cookie_set"]
                is False
            )
            print(
                json.dumps(
                    {
                        "extension": "unpacked Manifest V3",
                        "flows": [
                            "native server permission",
                            "connection test",
                            "activeTab action",
                            "generic selection and tags",
                            "XHS lazy comments without Cookie",
                            "Heybox comments without Cookie",
                            "comment limits and changed DOM",
                            "native context menu",
                            "large chunk upload after closing popup",
                            "actual service worker stop and queue resume",
                            "revoked Token error",
                        ],
                        "page_errors": errors,
                    },
                    ensure_ascii=False,
                )
            )
            assert errors == []
        finally:
            context.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="clipo-extension-") as directory:
        temp = Path(directory)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {key: value for key, value in os.environ.items() if not key.startswith("CLIPO_")}
        env.update(
            CLIPO_SECRET_KEY=secrets.token_hex(32),
            CLIPO_DATABASE_URL=f"sqlite:///{temp / 'test.db'}",
            CLIPO_QUEUE_PATH=str(temp / "queue.db"),
            CLIPO_BASE_URL=base,
            CLIPO_STATIC_PATH=str(temp / "no-static"),
            CLIPO_SMOKE_PORT=str(port),
        )
        # Fixture Settings ignores .env; migrations get every storage/security override here.
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
                display_number = next(
                    n for n in range(90, 120) if not Path(f"/tmp/.X{n}-lock").exists()
                )
                xvfb = subprocess.Popen(
                    [
                        "Xvfb",
                        f":{display_number}",
                        "-screen",
                        "0",
                        "1280x900x24",
                        "-nolisten",
                        "tcp",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=log,
                    text=True,
                )
                processes.append(xvfb)
                os.environ["DISPLAY"] = f":{display_number}"
                time.sleep(0.4)
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
                        api(base, "/health")
                        break
                    except OSError:
                        time.sleep(0.1)
                auth = api(
                    base,
                    "/setup",
                    body={
                        "username": "extension-test",
                        "email": "extension@example.com",
                        "password": "isolated-test-password",
                    },
                    method="POST",
                )["access_token"]
                token = api(base, "/tokens", auth, {"name": "extension-test"}, "POST")
                check_browser(base, auth, token, temp)
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
