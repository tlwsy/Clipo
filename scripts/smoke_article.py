# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""有序正文/卡片/扩展 DOM 离线验收，使用临时实例，不读取日常 Cookie。"""

import json
import os
import subprocess
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from smoke_backup import ACCOUNT, RESULTS, ROOT, launch, request

IMAGE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="920" height="430">'
    '<rect width="920" height="430" fill="#e4eee0"/>'
    '<rect x="40" y="40" width="840" height="350" rx="20" fill="#226552"/>'
    '<text x="80" y="240" fill="white" font-size="48">Clipo · Article</text></svg>'
)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    code = """import json
from app.extractors.xiaoheihe import parse_heybox
from pathlib import Path
html=Path('backend/tests/fixtures/xiaoheihe-rich.html').read_text()
c=parse_heybox(
    {'link':{'title':'结构阅读验收','text':json.dumps([{'type':'html','text':html}])}},
    'https://www.xiaoheihe.cn/app/bbs/link/123','',0,
    {'12345':{'steam_appid':12345,'game_type':'pc','name':'离线游戏 · 阅读卡片',
              'image':'https://heyboxbj.max-c.com/gameimg/steam_item_assets/offline.jpg'}})
print(json.dumps({'title':c.title,'text':c.text,
                  'blocks':[b.model_dump() for b in c.blocks],
                  'images':c.images},ensure_ascii=False))
"""
    payload = json.loads(
        subprocess.check_output([str(ROOT / ".venv/bin/python"), "-c", code], cwd=ROOT)
    )
    with tempfile.TemporaryDirectory(prefix="clipo-article-") as tmp, ExitStack() as stack:
        base = launch(stack, Path(tmp) / "instance")
        token = request(base, "/setup", body=ACCOUNT)["access_token"]
        job = request(
            base,
            "/captures",
            token,
            {"url": "https://www.xiaoheihe.cn/app/bbs/link/123", "payload": payload},
        )
        for _ in range(100):
            status = request(base, "/jobs/" + job["job_id"], token)
            if status["status"] == "success":
                break
            time.sleep(0.1)
        assert status["status"] == "success"
        note_id = status["note_id"]
        with sync_playwright() as pw, ExitStack() as browser_stack:
            browser = pw.chromium.launch(
                headless=True, executable_path=os.environ.get("CLIPO_TEST_CHROMIUM")
            )
            browser_stack.callback(browser.close)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.route(
                "https://**/*",
                lambda route: route.fulfill(content_type="image/svg+xml", body=IMAGE),
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间", exact=True).click()
            expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
            page.goto(base + f"/notes/?id={note_id}")
            article = page.locator(".article-content")
            expect(article.get_by_role("heading", name="第一章：离线教程")).to_be_visible()
            expect(article.locator("figure")).to_have_count(2)
            expect(article.locator("figcaption").first).to_have_text("步骤一：选择文件")
            expect(article.get_by_role("link", name="在 Steam 查看")).to_have_attribute(
                "href", "https://store.steampowered.com/app/12345/"
            )
            article.locator("summary").click()
            expect(article.get_by_text("折叠正文", exact=True)).to_be_visible()
            expect(article.locator("table th")).to_have_count(2)
            expect(article.locator("strong").first).to_have_text("保存")
            expect(article).not_to_contain_text("private-script")
            page.screenshot(path=str(RESULTS / "article-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            article.locator(".game-card").screenshot(path=str(RESULTS / "article-card-mobile.png"))
            page.screenshot(path=str(RESULTS / "article-mobile.png"), full_page=True)
            share = request(base, f"/notes/{note_id}/shares", token, {"expires_in_days": 1})
            public = browser.new_context(viewport={"width": 390, "height": 844})
            external = []
            public.route(
                "https://**/*",
                lambda route: route.fulfill(content_type="image/svg+xml", body=IMAGE),
            )
            public.on(
                "request",
                lambda req: external.append(req.url) if req.url.startswith("https:") else None,
            )
            shared = public.new_page()
            shared.goto(base + "/public/#" + share["token"])
            expect(shared.locator(".game-card")).to_be_visible()
            assert not external
            expect(shared.locator(".article-content img")).to_have_count(0)
            shared.get_by_role("button", name="加载原文图片").click()
            expect(shared.locator(".article-content img")).to_have_count(3)
            assert shared.evaluate("document.documentElement.scrollWidth <= innerWidth")
            # Run the exact self-contained extension collector against a realistic offline DOM.
            source = (
                (ROOT / "extension/content/extract.mjs")
                .read_text()
                .replace("export async function", "async function")
            )
            dom = browser.new_context()
            dom.route(
                "https://images.example.com/**",
                lambda route: route.fulfill(content_type="image/svg+xml", body=IMAGE),
            )
            fixture = (ROOT / "backend/tests/fixtures/extension-heybox-rich.html").read_text()
            dom.route(
                "https://www.xiaoheihe.cn/**",
                lambda route: route.fulfill(content_type="text/html", body=fixture),
            )
            source_page = dom.new_page()
            source_page.goto("https://www.xiaoheihe.cn/app/bbs/link/123")
            result = source_page.evaluate(
                "async () => {" + source + "; return await collectPage(1); }"
            )
            assert "error" not in result, result
            captured = result["payload"]
            assert (
                len(captured["comments"]) == 1 and captured["comments"][0]["content"] == "顶层评论"
            )
            assert captured["images"] == ["https://images.example.com/one.png"]
            assert "private-" not in json.dumps(captured)
            assert any(
                b["type"] == "game_card" and b["url"] == "https://store.steampowered.com/app/12345/"
                for b in captured["blocks"]
            )
            direct = request(base, "/captures", token, result)
            assert direct["job_id"]
            assert not errors, errors
    print("有序正文、手机卡片、公开图片加载控制及扩展 DOM 离线验收通过")


if __name__ == "__main__":
    main()
