# SPDX-License-Identifier: AGPL-3.0-or-later
"""阅读外观验收；--online-fonts 显式允许访问 Fontsource 和 jsDelivr。"""

import argparse
import json
import os
import struct
import tempfile
import zlib
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import Route, expect, sync_playwright
from smoke_annotations import wait_job
from smoke_backup import ACCOUNT, RESULTS, launch, request


def png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + bytes((227, 93, 106)) * 8) * 8))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online-fonts", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipo-appearance-") as tmp, ExitStack() as stack:
        base = launch(stack, Path(tmp) / "instance")
        token = request(
            base,
            "/setup",
            body={**ACCOUNT, "llm": {"api_key": "offline-only", "model": "offline-default"}},
        )["access_token"]
        text = (
            "\n\n".join(
                f"第 {index + 1} 段：让值得记住的内容，成为自己的知识。在字里行间，发现新的想法。"
                * 2
                for index in range(32)
            )
            + "\n\n完整正文的最后一段，也应该出现在预览中。"
        )
        note_id = wait_job(
            base,
            token,
            request(
                base,
                "/captures",
                token,
                {
                    "url": "https://example.com/reading-appearance",
                    "payload": {"title": "让阅读，回到舒服的节奏", "text": text},
                },
            ),
        )
        with sync_playwright() as pw, ExitStack() as browsers:
            browser = pw.chromium.launch(
                headless=True, executable_path=os.environ.get("CLIPO_TEST_CHROMIUM")
            )
            browsers.callback(browser.close)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors: list[str] = []
            external: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request", lambda req: external.append(req.url) if "fontsource" in req.url else None
            )
            if not args.online_fonts:
                catalog = [
                    {
                        "id": "noto-sans-sc",
                        "family": "Noto Sans SC",
                        "weights": [400, 500, 600, 700],
                        "subsets": ["chinese-simplified", "latin"],
                        "styles": ["normal"],
                        "variable": True,
                    },
                    {
                        "id": "inter",
                        "family": "Inter",
                        "weights": [400, 500, 600, 700],
                        "subsets": ["latin"],
                        "styles": ["normal"],
                        "variable": True,
                    },
                ]
                catalog_calls = {"count": 0}

                def catalog_response(route: Route) -> None:
                    catalog_calls["count"] += 1
                    if catalog_calls["count"] == 1:
                        route.abort()
                    else:
                        route.fulfill(json=catalog)

                page.route("https://api.fontsource.org/v1/fonts", catalog_response)
                page.route(
                    "https://api.fontsource.org/v1/version/*",
                    lambda route: route.fulfill(json={"latestVariable": "5.3.1"}),
                )
                page.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
            page.goto(base + "/login/")
            page.get_by_label("用户名").fill(ACCOUNT["username"])
            page.get_by_label("密码", exact=True).fill(ACCOUNT["password"])
            page.get_by_role("button", name="登录你的空间").click()
            expect(page.get_by_role("heading", name="你的笔记.")).to_be_visible()
            page.goto(base + f"/notes/?id={note_id}")
            page.get_by_role("button", name="阅读样式", exact=True).click()
            style = page.get_by_role("dialog", name="阅读样式")
            paper = style.get_by_role("region", name="阅读效果预览")
            expect(paper).to_contain_text("完整正文的最后一段")
            paper.evaluate("el => el.scrollTop = 180")
            expect(paper).to_have_js_property("scrollTop", 180)
            style.get_by_role("button", name="柔绿", exact=True).click()
            expect(paper).to_have_css("background-color", "rgb(232, 240, 230)")
            expect(paper).to_have_js_property("scrollTop", 180)
            style.get_by_role("tab", name="字体", exact=True).click()
            expect(style.get_by_role("button", name="适中", exact=True)).to_be_disabled()
            style.get_by_role("button", name="在线字体库", exact=False).click()
            if not args.online_fonts:
                expect(style.get_by_role("alert")).to_contain_text("暂时连不上字体库")
                style.get_by_role("button", name="重试字体目录").click()
            search = style.get_by_label("搜索在线字体")
            search.fill("思源黑体")
            online = style.get_by_role("group", name="在线字体", exact=True)
            expect(
                online.get_by_role("button", name="思源黑体 · 简体中文", exact=False).first
            ).to_be_visible(timeout=30000)
            online.get_by_role("button", name="思源黑体 · 简体中文", exact=False).first.click()
            expected_status = "ready" if args.online_fonts else "error"
            expect(style.locator("[data-font-status]")).to_have_attribute(
                "data-font-status", expected_status, timeout=60000
            )
            expect(style.get_by_role("button", name="适中", exact=True)).to_be_enabled()
            if args.online_fonts:
                masses = []
                for weight, label in ((400, "标准"), (500, "适中"), (600, "半粗"), (700, "加粗")):
                    style.get_by_role("button", name=label, exact=True).click()
                    expect(paper.locator(".article-content")).to_have_css(
                        "font-weight", str(weight)
                    )
                    mass = page.evaluate(
                        """async weight => {
                      const family = 'Noto Sans SC Variable';
                      const sample = '阅读时光知行合一';
                      await document.fonts.load(`${weight} 32px "${family}"`, sample);
                      const canvas = document.createElement('canvas');
                      canvas.width=400; canvas.height=60;
                      const ctx = canvas.getContext('2d'); ctx.font=`${weight} 32px "${family}"`;
                      ctx.fillText(sample, 4, 40);
                      return ctx.getImageData(0,0,400,60).data.reduce(
                        (sum, value, i) => sum + (i%4===3 ? value : 0), 0);
                    }""",
                        weight,
                    )
                    masses.append(mass)
                assert all(a < b for a, b in zip(masses, masses[1:], strict=False)), masses
                print("在线中文可变字体四档墨迹量：", masses)
            else:
                style.get_by_role("button", name="重试字体下载").click()
                expect(style.locator("[data-font-status]")).to_have_attribute(
                    "data-font-status", "error"
                )
            search.fill("Inter")
            expect(style.get_by_text("没有找到字体，试试英文名称或全部语言。")).to_be_visible()
            style.get_by_role("button", name="全部语言", exact=True).click()
            expect(online.get_by_role("button", name="Inter", exact=False).first).to_be_visible()
            if not args.online_fonts:
                pending: list[Route] = []
                page.route(
                    "https://api.fontsource.org/v1/version/inter",
                    lambda route: pending.append(route),
                )
                online.get_by_role("button", name="Inter", exact=False).first.click()
                expect(style.get_by_role("button", name="保存样式")).to_be_disabled()
                style.get_by_role("tab", name="主题", exact=True).click()
                style.get_by_role("button", name="舒适", exact=True).click()
                page.wait_for_timeout(100)
                assert pending
                pending[0].fulfill(json={"latestVariable": "5.3.1"})
                style.get_by_role("tab", name="字体", exact=True).click()
                expect(style.get_by_role("button", name="系统字体", exact=False)).to_have_attribute(
                    "aria-pressed", "true"
                )
                expect(style.get_by_role("button", name="保存样式")).to_be_enabled()
                style.get_by_role("button", name="在线字体库", exact=False).click()
                search.fill("思源黑体")
                online.get_by_role("button", name="思源黑体 · 简体中文", exact=False).first.click()
                expect(style.locator("[data-font-status]")).to_have_attribute(
                    "data-font-status", "error"
                )
            search.fill("")
            before = paper.bounding_box()
            style.locator(".style-controls").evaluate("el => el.scrollTop = el.scrollHeight")
            after = paper.bounding_box()
            assert before == after, (before, after)
            workspace = style.locator(".style-workspace").bounding_box()
            assert after["y"] + after["height"] > workspace["y"] + workspace["height"] - 70
            page.screenshot(path=str(RESULTS / "reading-online-fonts-desktop.png"))
            style.get_by_role("tab", name="主题", exact=True).click()
            style.get_by_role("button", name="莫奈取色", exact=True).click()
            style.get_by_label("从图片取色", exact=True).set_input_files(
                {"name": "rose.png", "mimeType": "image/png", "buffer": png()}
            )
            expect(style.get_by_label("莫奈种子色")).to_have_value("#e35d6a")
            style.get_by_role("button", name="浅色", exact=True).click()
            light = paper.evaluate(
                "el => getComputedStyle(el).getPropertyValue('--reading-background')"
            )
            style.get_by_role("button", name="深色", exact=True).click()
            dark = paper.evaluate(
                "el => getComputedStyle(el).getPropertyValue('--reading-background')"
            )
            assert light != dark
            style.get_by_role("button", name="随系统", exact=True).click()
            page.emulate_media(color_scheme="dark")
            expect(paper).to_have_css("color-scheme", "dark")
            page.emulate_media(color_scheme="light")
            expect(paper).to_have_css("color-scheme", "light")
            page.screenshot(path=str(RESULTS / "reading-monet-desktop.png"))
            style.get_by_role("button", name="保存样式").click()
            expect(style).to_have_count(0)
            saved = request(base, f"/notes/{note_id}", token)["display_overrides"]
            assert saved["monet_seed"] == "#e35d6a" and saved["color_mode"] == "monet"
            assert saved["online_font"]["id"] == "noto-sans-sc"
            page.reload()
            expect(page.locator("article.reader")).to_have_css("color-scheme", "light")
            page.emulate_media(color_scheme="dark")
            expect(page.locator("article.reader")).to_have_css("color-scheme", "dark")
            page.get_by_role("button", name="阅读样式", exact=True).click()
            style.get_by_role("button", name="跟随系统", exact=True).click()
            expect(paper).to_have_css("background-color", "rgb(32, 36, 33)")
            style.get_by_role("button", name="保存样式").click()
            expect(page.locator("article.reader")).to_have_css(
                "background-color", "rgb(32, 36, 33)"
            )
            page.emulate_media(color_scheme="light")
            expect(page.locator("article.reader")).to_have_css(
                "background-color", "rgb(250, 251, 247)"
            )
            page.get_by_role("button", name="阅读样式", exact=True).click()
            style.get_by_role("button", name="莫奈取色", exact=True).click()
            for width, height in ((320, 740), (390, 844), (768, 1024), (844, 390)):
                page.set_viewport_size({"width": width, "height": height})
                for tab in ("字体", "排版", "主题"):
                    style.get_by_role("tab", name=tab, exact=True).click()
                    assert style.evaluate("el => el.scrollWidth <= el.clientWidth")
                    expect(style.get_by_role("button", name="保存样式")).to_be_in_viewport()
                    expect(paper).to_be_in_viewport()
                    assert paper.bounding_box()["height"] > 50
                    style.locator(".style-controls").evaluate(
                        "el => el.scrollTop = el.scrollHeight"
                    )
                    expect(paper).to_be_in_viewport()
                if width == 390:
                    page.screenshot(path=str(RESULTS / "reading-monet-mobile.png"))
            page.emulate_media(reduced_motion="reduce")
            style.get_by_role("tab", name="排版", exact=True).click()
            style.get_by_label("字号", exact=False).fill("24")
            assert paper.evaluate("el => el.getAnimations({subtree:true}).length") == 0
            expect(paper).to_have_css("transition-duration", "0s")
            page.keyboard.press("Escape")
            assert (
                request(base, f"/notes/{note_id}", token)["display_overrides"]["color_mode"]
                == "system"
            )
            assert all("example.com" not in url and "%E7%AC%AC" not in url for url in external)
            assert not errors, errors
            print(
                "阅读外观验收通过：完整预览、独立滚动、在线字体搜索/失败回退、莫奈图片取色、系统明暗、保存刷新、减少动态效果及多视口。"
            )
            print(
                json.dumps({"online_fonts": args.online_fonts, "external_requests": len(external)})
            )


if __name__ == "__main__":
    main()
