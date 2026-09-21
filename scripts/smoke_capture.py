"""Browser acceptance with a temporary database and offline HTML/model fixtures.

Run after `make build`: uv run --no-project --with playwright python scripts/smoke_capture.py
Install Chromium with `uv run --no-project --with playwright playwright install chromium` if needed.
"""

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def check_platform_settings(page: Page) -> None:
    card = page.locator("#platforms")
    xhs = card.get_by_label("小红书 Cookie", exact=True)
    heybox = card.get_by_label("小黑盒 Cookie", exact=True)
    save = card.get_by_role("button", name="保存平台配置")
    expect(save).to_be_disabled()
    xhs.fill("web_session=offline-xhs-session")
    heybox.fill("session=offline-heybox-session")
    save.click()
    expect(card.get_by_role("status")).to_contain_text("尚未验证登录有效性")
    expect(xhs).to_have_value("")
    expect(heybox).to_have_value("")
    page.reload()
    expect(card.get_by_text("已保存，未验证", exact=True)).to_have_count(2)
    xhs.fill("web_session=replaced-offline-session")
    save.click()
    expect(card.get_by_role("status")).to_be_visible()
    expect(card.get_by_text("已保存，未验证", exact=True)).to_have_count(2)
    page.reload()
    card.get_by_label("清除小红书 Cookie").check()
    expect(xhs).to_be_disabled()
    save.click()
    expect(card.get_by_text("尚未配置", exact=True)).to_have_count(1)
    expect(card.get_by_text("已保存，未验证", exact=True)).to_have_count(1)
    xhs.fill("web_session=retry-offline-session")
    page.route(
        "**/api/v1/settings",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"error": {"message": "测试保存失败，请重试"}}),
        ),
    )
    save.click()
    expect(card.get_by_role("alert")).to_have_text("测试保存失败，请重试")
    expect(xhs).to_have_value("web_session=retry-offline-session")
    page.unroute("**/api/v1/settings")
    save.click()
    expect(card.get_by_role("status")).to_be_visible()
    expect(xhs).to_have_value("")
    card.get_by_label("清除小红书 Cookie").check()
    card.get_by_label("清除小黑盒 Cookie").check()
    save.click()
    expect(card.get_by_text("尚未配置", exact=True)).to_have_count(2)
    page.reload()
    expect(card.get_by_text("尚未配置", exact=True)).to_have_count(2)
    expect(page.locator("#llm")).to_contain_text("已配置密钥")
    card.get_by_text("如何获取小红书 Cookie", exact=True).click()
    expect(card.get_by_role("link", name="小红书官网")).to_be_visible()
    screenshots = ROOT / "frontend/test-results"
    screenshots.mkdir(exist_ok=True)
    card.screenshot(path=str(screenshots / "platform-settings-desktop.png"))
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    card.screenshot(path=str(screenshots / "platform-settings-mobile.png"))
    page.set_viewport_size({"width": 1440, "height": 1000})


def check_platform_probes(page: Page) -> None:
    card = page.locator("#platforms")
    xhs = card.locator("#xiaohongshu-cookie-status")
    heybox = card.locator("#xiaoheihe-cookie-status")
    card.get_by_label("小红书 Cookie", exact=True).fill("session=offline-expired")
    card.get_by_label("小黑盒 Cookie", exact=True).fill("session=offline-heybox")
    expect(card.get_by_role("button", name="检测小红书登录状态")).to_be_disabled()
    card.get_by_role("button", name="保存平台配置").click()
    expect(card.get_by_role("status")).to_be_visible()
    card.get_by_role("button", name="检测小红书登录状态").click()
    expect(xhs).to_have_text("登录态失效", timeout=20000)
    card.get_by_role("button", name="检测小黑盒登录状态").click()
    expect(heybox).to_have_text("登录有效", timeout=20000)
    page.reload()
    expect(xhs).to_have_text("登录态失效")
    expect(heybox).to_have_text("登录有效")
    card.get_by_label("小红书 Cookie", exact=True).fill("web_session=offline-capture")
    card.get_by_label("小黑盒 Cookie", exact=True).fill("session=offline-restricted")
    card.get_by_role("button", name="保存平台配置").click()
    expect(xhs).to_have_text("已保存，未验证")
    expect(heybox).to_have_text("已保存，未验证")
    card.get_by_role("button", name="检测小红书登录状态").click()
    expect(xhs).to_have_text("登录有效", timeout=20000)
    card.get_by_role("button", name="检测小黑盒登录状态").click()
    expect(heybox).to_have_text("未能确认登录状态", timeout=20000)
    expect(card.get_by_text("小黑盒限制访问", exact=False)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    card.screenshot(path=str(ROOT / "frontend/test-results/platform-checks-mobile.png"))
    page.set_viewport_size({"width": 1440, "height": 1000})
    card.get_by_label("清除小红书 Cookie").check()
    card.get_by_label("清除小黑盒 Cookie").check()
    card.get_by_role("button", name="保存平台配置").click()
    expect(xhs).to_have_text("尚未配置")
    expect(heybox).to_have_text("尚未配置")


def check_capture_settings(page: Page) -> None:
    card = page.locator("#capture")
    limit = card.get_by_label("评论采集上限")
    save = card.get_by_role("button", name="保存采集配置")
    expect(limit).to_have_value("100")
    for value in ("", "-1", "101", "1.5"):
        limit.fill(value)
        save.click()
        assert limit.evaluate("input => !input.validity.valid")
    limit.fill("7")
    page.route(
        "**/api/v1/settings",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"error": {"message": "测试保存失败，请重试"}}),
        ),
    )
    save.click()
    expect(card.get_by_role("alert")).to_have_text("测试保存失败，请重试")
    expect(limit).to_have_value("7")
    page.unroute("**/api/v1/settings")
    save.click()
    expect(card.get_by_role("status")).to_contain_text("采集配置已保存")
    page.reload()
    expect(limit).to_have_value("7")
    expect(page.get_by_label("候选评论上限")).to_have_value("30")
    screenshots = ROOT / "frontend/test-results"
    card.screenshot(path=str(screenshots / "capture-settings-desktop.png"))
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    card.screenshot(path=str(screenshots / "capture-settings-mobile.png"))
    page.set_viewport_size({"width": 1440, "height": 1000})
    limit.fill("100")
    save.click()
    expect(card.get_by_role("status")).to_be_visible()


def check_xiaohongshu_capture(page: Page, base: str) -> None:
    page.goto(base + "/")
    page.get_by_label("网页链接").fill("https://www.xiaohongshu.com/explore/64abc123")
    page.get_by_role("button", name="保存网页").click()
    job = page.locator(".job-card").filter(has_text="www.xiaohongshu.com/explore/64abc123")
    expect(job.locator(".job-status.failed")).to_be_visible(timeout=20000)
    expect(job).to_contain_text("登录态失效")
    page.goto(base + "/settings/")
    page.get_by_label("候选评论上限").fill("2")
    page.get_by_label("高价值评论阈值").fill("0.7")
    page.get_by_role("button", name="保存配置", exact=True).click()
    expect(page.locator("#llm .notice.success")).to_be_visible()
    page.reload()
    expect(page.get_by_label("候选评论上限")).to_have_value("2")
    expect(page.get_by_label("高价值评论阈值")).to_have_value("0.7")
    page.get_by_label("小红书 Cookie", exact=True).fill("web_session=offline-capture")
    page.get_by_role("button", name="保存平台配置").click()
    expect(page.locator("#platforms").get_by_role("status")).to_be_visible()
    page.goto(base + "/jobs/")
    job.get_by_role("button", name="重新保存", exact=True).click()
    expect(job.locator(".job-status.success")).to_be_visible(timeout=20000)
    job.get_by_role("link", name="阅读笔记").click()
    expect(page.get_by_role("heading", name="离线采集笔记")).to_be_visible()
    expect(page.locator(".reader-meta")).to_contain_text("离线作者")
    expect(page.locator(".original-text")).to_contain_text("保留正文与来源")
    expect(page.locator(".comment")).to_have_count(10)
    expect(page.locator(".comment").first).to_contain_text("12 赞 · 2 回复")
    expect(page.get_by_text("采集到的评论可能不完整。", exact=True)).to_be_visible()
    expect(page.get_by_text("已评分 2 / 10 条", exact=False)).to_be_visible()
    expect(page.locator(".comment .pill")).to_have_count(1)
    expect(page.locator(".comment").first).to_contain_text("AI 评分 0.9")
    expect(page.locator(".comment").nth(1)).to_contain_text("AI 评分 0.6")
    expect(page.locator(".comment").nth(2)).to_contain_text("未评分")
    expect(page.locator(".comment").first).to_contain_text("提供了可操作的补充建议")
    expect(page.get_by_role("link", name="查看图片")).to_have_count(2)
    screenshots = ROOT / "frontend/test-results"
    page.screenshot(path=str(screenshots / "xiaohongshu-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(screenshots / "xiaohongshu-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})

    # Reuse the cached extraction with a model that omits scores: retain the summary and comments.
    page.goto(base + "/settings/")
    page.get_by_label("模型名称").fill("offline-no-scores")
    page.get_by_role("button", name="保存配置", exact=True).click()
    expect(page.locator("#llm .notice.success")).to_be_visible()
    page.goto(base + "/")
    page.get_by_label("网页链接").fill("https://www.xiaohongshu.com/explore/64abc123")
    page.get_by_role("button", name="保存网页").click()
    latest = page.locator(".job-card").filter(has_text="www.xiaohongshu.com/explore/64abc123").first
    expect(latest.locator(".job-status.success")).to_be_visible(timeout=20000)
    latest.get_by_role("link", name="阅读笔记").click()
    expect(page.locator(".markdown")).to_be_visible()
    expect(
        page.get_by_text("未生成评论评分：模型服务不可用或评分格式无效", exact=False)
    ).to_be_visible()
    expect(page.locator(".comment")).to_have_count(10)
    expect(page.locator(".comment .pill")).to_have_count(0)
    expect(page.get_by_text("已评分 0 / 10 条", exact=False)).to_be_visible()


def check_comment_capture_limit(page: Page, base: str) -> None:
    url = "https://www.xiaohongshu.com/explore/64abc123?capture-limit=offline"
    original_note_url = ""
    for limit in (3, 0, 6):
        page.goto(base + "/settings/")
        page.get_by_label("评论采集上限").fill(str(limit))
        page.get_by_role("button", name="保存采集配置").click()
        expect(page.locator("#capture").get_by_role("status")).to_be_visible()
        page.reload()
        expect(page.get_by_label("评论采集上限")).to_have_value(str(limit))
        expect(page.get_by_label("候选评论上限")).to_have_value("2")
        page.get_by_label("模型名称").fill("offline-scores")
        page.get_by_role("button", name="保存配置", exact=True).click()
        expect(page.locator("#llm .notice.success")).to_be_visible()
        page.goto(base + "/")
        page.get_by_label("网页链接").fill(url)
        page.get_by_role("button", name="保存网页").click()
        job = page.locator(".job-card").filter(has_text=url).first
        expect(job.locator(".job-status.success")).to_be_visible(timeout=20000)
        job.get_by_role("link", name="阅读笔记").click()
        expect(page.locator(".comment")).to_have_count(limit)
        expect(page.locator(".markdown")).to_be_visible()
        expect(page.locator(".original-text")).to_contain_text("保留正文与来源")
        if limit:
            expect(page.get_by_text(f"本次评论采集上限：{limit} 条。")).to_be_visible()
            expect(page.get_by_text(f"已评分 2 / {limit} 条", exact=False)).to_be_visible()
        else:
            expect(page.get_by_text("本次已关闭评论采集，帖子内容已保存。")).to_be_visible()
            expect(page.get_by_text("未生成评论评分", exact=False)).to_have_count(0)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(
                path=str(ROOT / "frontend/test-results/comments-disabled-mobile.png"),
                full_page=True,
            )
            page.set_viewport_size({"width": 1440, "height": 1000})
        if limit == 3:
            original_note_url = page.url
    page.goto(original_note_url)
    expect(page.locator(".comment")).to_have_count(3)
    expect(page.get_by_text("本次评论采集上限：3 条。")).to_be_visible()


def check_xhs_pagination(page: Page, base: str) -> None:
    page.goto(base + "/settings/")
    page.get_by_label("评论采集上限").fill("100")
    page.get_by_role("button", name="保存采集配置").click()
    expect(page.locator("#capture").get_by_role("status")).to_be_visible()
    page.goto(base + "/")
    page.get_by_label("网页链接").fill("https://xhslink.cn/o/offline")
    page.get_by_role("button", name="保存网页").click()
    job = page.locator(".job-card").filter(has_text="https://xhslink.cn/o/offline").first
    expect(job.locator(".job-status.success")).to_be_visible(timeout=20000)
    job.get_by_role("link", name="阅读笔记").click()
    expect(page.locator(".comment")).to_have_count(12)
    expect(page.locator(".comment").nth(10)).to_contain_text("分页读者")
    expect(page.get_by_text("已评分 2 / 12 条", exact=False)).to_be_visible()
    expect(page.locator(".comment .pill")).to_have_count(1)


def check_heybox_capture(page: Page, base: str) -> None:
    url = "https://api.xiaoheihe.cn/v3/bbs/app/api/web/share?link_id=opaque123"
    page.goto(base + "/")
    page.get_by_label("网页链接").fill(url)
    page.get_by_role("button", name="保存网页").click()
    job = page.locator(".job-card").filter(has_text=url).first
    expect(job.locator(".job-status.success")).to_be_visible(timeout=20000)
    job.get_by_role("link", name="阅读笔记").click()
    expect(page.get_by_role("heading", name="离线小黑盒笔记")).to_be_visible()
    expect(page.locator(".original-text")).to_contain_text("保存游戏攻略")
    expect(page.locator(".comment")).to_have_count(12)
    expect(page.get_by_text("已评分 2 / 12 条", exact=False)).to_be_visible()
    expect(page.locator(".comment .pill")).to_have_count(1)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(ROOT / "frontend/test-results/heybox-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})


def check_bilibili_capture(page: Page, base: str) -> None:
    url = "https://www.bilibili.com/video/BV1xx411c7mD?p=2"
    page.goto(base + "/")
    page.get_by_label("网页链接").fill(url)
    page.get_by_role("button", name="保存网页").click()
    job = page.locator(".job-card").filter(has_text=url).first
    expect(job.locator(".job-status.success")).to_be_visible(timeout=20000)
    job.get_by_role("link", name="阅读笔记").click()
    expect(page.get_by_role("heading", name="离线视频笔记")).to_be_visible()
    expect(page.locator(".original-text")).to_contain_text("字幕（中文）")
    expect(page.locator(".comment")).to_have_count(23)
    expect(page.get_by_text("已评分 2 / 23 条", exact=False)).to_be_visible()


def check_youtube_capture(page: Page, base: str) -> None:
    url = "https://youtu.be/abcDEF123_-"
    page.goto(base + "/")
    page.get_by_label("网页链接").fill(url)
    page.get_by_role("button", name="保存网页").click()
    job = page.locator(".job-card").filter(has_text=url).first
    expect(job.locator(".job-status.success")).to_be_visible(timeout=20000)
    job.get_by_role("link", name="阅读笔记").click()
    expect(page.get_by_role("heading", name="离线 YouTube 视频")).to_be_visible()
    expect(page.locator(".original-text")).to_contain_text("First save the source.")
    expect(page.locator(".original-text")).to_contain_text("字幕（en，自动字幕）")
    expect(page.locator(".comment")).to_have_count(3)
    expect(page.get_by_text("已评分 2 / 3 条", exact=False)).to_be_visible()
    expect(page.locator(".comment").last).to_contain_text("Modern comment")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(ROOT / "frontend/test-results/youtube-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})


def check_note_organization(page: Page, base: str) -> None:
    page.get_by_role("button", name="☆ 标记收藏").click()
    expect(page.get_by_role("button", name="★ 已收藏")).to_be_visible()
    page.get_by_label("添加标签", exact=True).fill("阶段四验收")
    page.get_by_role("button", name="添加", exact=True).click()
    expect(page.get_by_role("button", name="移除标签 阶段四验收")).to_be_visible()
    page.goto(base + "/")
    page.get_by_label("按标签筛选").select_option(label="阶段四验收")
    page.get_by_label("只看收藏").check()
    page.get_by_label("搜索笔记").fill("离线")
    page.get_by_role("button", name="搜索", exact=True).click()
    expect(page.locator(".note-card")).to_have_count(1)
    page.locator(".note-card").click()
    page.get_by_role("button", name="移除标签 阶段四验收").click()
    expect(page.get_by_role("button", name="移除标签 阶段四验收")).to_have_count(0)
    page.reload()
    expect(page.get_by_role("button", name="★ 已收藏")).to_be_visible()


def check_offline_notes(page: Page, base: str, static: Path) -> None:
    context = page.context
    page.goto(base + "/")
    expect(page.locator(".note-card").first).to_be_visible()
    page.locator(".note-card").first.click()
    expect(page.locator(".original-text")).to_be_visible()
    note_url = page.url
    expect(page.locator(".offline-status")).to_contain_text(
        re.compile(r"离线可读 [1-9]"), timeout=20000
    )
    page.evaluate("navigator.serviceWorker.ready")
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    # Only public shells/assets may enter the service-worker cache.
    assert page.evaluate("""async () => {
        for (const name of await caches.keys()) {
            for (const request of await (await caches.open(name)).keys()) {
                if (new URL(request.url).pathname.startsWith('/api/')) return false;
            }
        }
        return true;
    }""")
    context.set_offline(True)
    page.reload()
    expect(page.locator(".original-text")).to_be_visible()
    expect(page.locator(".offline-status")).to_contain_text("离线阅读")
    favorite = page.get_by_role("button", name="☆ 标记收藏")
    if favorite.count():
        favorite.click()
        expect(page.get_by_role("button", name="★ 已收藏")).to_be_visible()
    page.get_by_role("button", name="删除笔记").click()
    page.get_by_role("button", name="确认删除").click()
    expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
    expect(page.locator(".offline-status")).to_contain_text("操作待同步")
    page.reload()
    expect(page.locator(".offline-status")).to_contain_text("操作待同步")
    page.get_by_label("网页链接").fill("https://example.com/offline-capture")
    page.get_by_role("button", name="保存网页").click()
    expect(page.get_by_role("heading", name="保存队列.")).to_be_visible()
    context.set_offline(False)
    expect(page.locator(".offline-status")).not_to_contain_text("操作待同步", timeout=30000)
    job = page.locator(".job-card").filter(has_text="https://example.com/offline-capture")
    expect(job.locator(".job-status.success")).to_be_visible(timeout=20000)
    page.goto(note_url)
    expect(page.locator(".notice.error")).to_contain_text("笔记不存在")
    page.goto(base + "/")
    context.set_offline(True)
    page.get_by_label("网页链接").fill("https://127.0.0.1/private")
    page.get_by_role("button", name="保存网页").click()
    expect(page.get_by_role("heading", name="保存队列.")).to_be_visible()
    context.set_offline(False)
    expect(page.get_by_role("button", name="取消失败操作")).to_be_visible(timeout=20000)
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="取消失败操作").click()
    expect(page.locator(".offline-status")).not_to_contain_text("操作待同步")
    # A changed SW must wait until the user accepts the update.
    script = static / "sw.js"
    original = script.read_text()
    try:
        script.write_text(original + "\n// browser acceptance update\n")
        page.evaluate("async () => (await navigator.serviceWorker.ready).update()")
        expect(page.get_by_role("button", name="刷新应用")).to_be_visible(timeout=20000)
        with page.expect_navigation(wait_until="networkidle"):
            page.get_by_role("button", name="刷新应用").click()
        expect(page.get_by_role("button", name="刷新应用")).to_have_count(0)
    finally:
        script.write_text(original)
    page.goto(base + "/")
    expect(page.locator(".note-card").first).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(ROOT / "frontend/test-results/phase4-mobile.png"), full_page=True)
    page.get_by_role("button", name="退出登录").last.click()
    expect(page.get_by_role("heading", name="欢迎回到 Clipo")).to_be_visible()
    assert page.evaluate("""() => new Promise((resolve, reject) => {
        const request = indexedDB.open('clipo-offline', 1);
        request.onsuccess = () => {
            const tx = request.result.transaction(['notes','operations','meta']);
            const query = tx.objectStore('meta').get('account');
            query.onsuccess = () => resolve(query.result === undefined);
        };
        request.onerror = reject;
    })""")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="clipo-capture-browser-") as directory:
        temp = Path(directory)
        shutil.copytree(ROOT / "backend/app/static", temp / "static")
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
            CLIPO_STATIC_PATH=str(temp / "static"),
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
                    check_platform_settings(page)
                    check_platform_probes(page)
                    check_capture_settings(page)
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
                    check_xiaohongshu_capture(page, base)
                    check_comment_capture_limit(page, base)
                    check_xhs_pagination(page, base)
                    check_heybox_capture(page, base)
                    check_bilibili_capture(page, base)
                    check_youtube_capture(page, base)
                    check_note_organization(page, base)
                    manifest = context.request.get(base + "/manifest.webmanifest").json()
                    assert manifest["share_target"]["action"] == "/share/"
                    for icon in manifest["icons"]:
                        assert context.request.get(base + icon["src"]).status == 200
                    page.evaluate("navigator.serviceWorker.ready")
                    check_offline_notes(page, base, temp / "static")
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
                                    "platform Cookie save, replace, clear and retry",
                                    "platform login checks, expired and restricted states",
                                    "Xiaohongshu login failure, Cookie retry and comment scores",
                                    "comment limits, disable, cache and larger recapture",
                                    "XHS .cn short link and two comment API pages",
                                    "Heybox share link, pagination and comment scores",
                                    "Bilibili video, captions and paginated hot comments",
                                    "YouTube captions, top sort, old and modern comments",
                                    "delete",
                                    "manual retry",
                                    "share through login",
                                    "mobile layout",
                                    "manifest and service worker",
                                    "tags, favorites and Chinese search",
                                    "offline reload, queued writes, replay and cancel failure",
                                    "service worker update prompt and logout cache cleanup",
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
