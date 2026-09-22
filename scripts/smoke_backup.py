"""两个临时实例的浏览器备份恢复验收，仅使用虚构数据和离线模型。"""

import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "frontend/test-results"
ACCOUNT = {
    "username": "backup-demo",
    "email": "demo@example.com",
    "password": "offline-backup-demo-123",
}


def request(base: str, path: str, token: str = "", body: Any = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(
        urllib.request.Request(base + "/api/v1" + path, payload, headers), timeout=10
    ) as response:
        return json.load(response)


def launch(stack: ExitStack, directory: Path) -> str:
    directory.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {key: value for key, value in os.environ.items() if not key.startswith("CLIPO_")}
    env.update(
        CLIPO_SECRET_KEY=secrets.token_hex(32),
        CLIPO_DATABASE_URL=f"sqlite:///{directory / 'test.db'}",
        CLIPO_QUEUE_PATH=str(directory / "huey.db"),
        CLIPO_BASE_URL=base,
        CLIPO_BACKUP_PATH=str(directory / "backups"),
        CLIPO_STATIC_PATH=str(ROOT / "backend/app/static"),
        CLIPO_SMOKE_PORT=str(port),
    )
    # Migrations use explicit test settings rather than the working deployment's .env.
    subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "-c",
            "from alembic import command; from alembic.config import Config; "
            "from app.config import Settings; from app.db.session import create_db_engine; "
            "engine=create_db_engine(Settings(_env_file=None)); "
            "config=Config('backend/alembic.ini'); "
            "connection=engine.connect(); config.attributes['connection']=connection; "
            "command.upgrade(config, 'head'); connection.commit(); "
            "connection.close(); engine.dispose()",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    log = stack.enter_context((directory / "server.log").open("w"))
    for mode in ("api", "worker"):
        process = subprocess.Popen(
            [str(ROOT / ".venv/bin/python"), str(ROOT / "backend/tests/browser/server.py"), mode],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
        stack.callback(stop, process)
    for _ in range(100):
        try:
            request(base, "/health")
            return base
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("临时 API 未能启动，请检查验收日志")


def stop(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="clipo-backup-smoke-") as temporary,
        ExitStack() as stack,
    ):
        root = Path(temporary)
        source, destination = launch(stack, root / "source"), launch(stack, root / "destination")
        token = request(source, "/setup", body=ACCOUNT)["access_token"]
        destination_token = request(destination, "/setup", body=ACCOUNT)["access_token"]
        payload = {
            "url": "https://example.com/knowledge",
            "payload": {
                "title": "让知识在需要时出现",
                "text": "保存阅读中有用的观点，保留出处，并把它变成下一次行动。",
                "images": ["https://example.com/cover.jpg"],
                "tags": ["知识管理"],
                "comments": [
                    {
                        "author": "读者",
                        "content": "每周回顾比单纯收藏更有帮助",
                        "likes": 12,
                        "replies": 1,
                    }
                ],
            },
        }
        job = request(source, "/captures", token, payload)
        for _ in range(100):
            status = request(source, "/jobs/" + job["job_id"], token)
            if status["status"] == "success":
                break
            time.sleep(0.1)
        assert status["status"] == "success", status["status"]
        with sync_playwright() as playwright, ExitStack() as browser_stack:
            browser = playwright.chromium.launch(
                headless=True, executable_path=os.environ.get("CLIPO_TEST_CHROMIUM")
            )
            browser_stack.callback(browser.close)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900}, accept_downloads=True
            )
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(source + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间", exact=True).click()
            expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
            expect(page.locator(".note-card")).to_have_count(1)
            page.screenshot(path=str(RESULTS / "backup-demo-library.png"))
            page.locator(".note-card").first.click()
            expect(page.locator(".original-text")).to_contain_text("保存阅读")
            page.screenshot(path=str(RESULTS / "backup-demo-note.png"))
            page.goto(source + "/settings/#backups")
            panel = page.locator("#backups")
            panel.get_by_label("备份目标").select_option("local")
            panel.get_by_label("备份计划").fill("0 4 * * *")
            panel.get_by_role("button", name="保存备份配置").click()
            expect(panel.get_by_role("status")).to_have_text("备份配置已保存")
            panel.get_by_role("button", name="立即备份").click()
            expect(panel.get_by_text("备份 · 已完成", exact=True)).to_be_visible(timeout=20000)
            assert len(list((root / "source/backups/1").glob("*.zip"))) == 1
            panel.get_by_role("button", name="导出 JSON 与 Markdown").click()
            expect(panel.get_by_text("导出 · 已完成", exact=True)).to_be_visible(timeout=20000)
            with page.expect_download() as download:
                panel.get_by_role("button", name="下载 ZIP").first.click()
            data = Path(download.value.path()).read_bytes()
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                library = archive.read("library.json")
            panel.scroll_into_view_if_needed()
            page.screenshot(path=str(RESULTS / "backup-demo-settings.png"))
            page.set_viewport_size({"width": 390, "height": 844})
            panel.scroll_into_view_if_needed()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(RESULTS / "backup-mobile.png"))
            context.close()
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(destination + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间", exact=True).click()
            expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
            page.goto(destination + "/settings/#backups")
            panel = page.locator("#backups")
            panel.get_by_label("导入 library.json").set_input_files(
                {"name": "library.json", "mimeType": "application/json", "buffer": library}
            )
            panel.get_by_role("button", name="确认追加导入").click()
            expect(panel.get_by_text("导入 · 已完成", exact=True)).to_be_visible(timeout=20000)
            notes = request(destination, "/notes", destination_token)["items"]
            assert len(notes) == 1 and notes[0]["title"] == payload["payload"]["title"]
            restored = request(destination, f"/notes/{notes[0]['id']}", destination_token)
            assert restored["content"]["images"] == payload["payload"]["images"]
            assert restored["comments"][0]["likes"] == 12
            assert restored["tags"][0]["name"] == "知识管理"
            panel.get_by_label("导入 library.json").set_input_files(
                {"name": "library.json", "mimeType": "application/json", "buffer": library}
            )
            panel.get_by_role("button", name="确认追加导入").click()
            expect(panel.get_by_role("status")).to_contain_text("导入任务已提交")
            assert len(request(destination, "/notes", destination_token)["items"]) == 1
            assert not errors, errors
            context.close()
        shutil.copy(root / "source/server.log", RESULTS / "backup-source.log")
        print(
            "浏览器备份验收通过：本地目标、导出下载、空实例恢复、评论/标签/媒体引用、重复导入与手机布局"
        )


if __name__ == "__main__":
    main()
