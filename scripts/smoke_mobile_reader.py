# SPDX-License-Identifier: AGPL-3.0-or-later
"""M1 专项，由 smoke_mobile_android.py --reader 在隔离模拟器和临时 API 内调用。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from smoke_mobile_android import Device


def verify_reader(device: Device, base: str) -> None:
    """验证富文本、本文/全局样式、平板布局和 2 倍系统字体，不触碰真实账号。"""
    with httpx.Client(base_url=base + "/api/v1", trust_env=False) as client:
        response = client.post(
            "/auth/login", json={"username": "mobile-test", "password": "mobile-test-password"}
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        note_id = client.get("/notes").json()["items"][0]["id"]
        print("Android M1：原生富文本和折叠内容", flush=True)
        device.scroll_to("Rich heading")
        device.scroll_to("Column A")
        device.screenshot("m1-table")
        device.tap(device.scroll_to("More details"))
        device.scroll_to("Hidden paragraph")
        device.screenshot("m1-expanded")
        device.press("阅读样式", "Reading style")
        device.press("全局", "Global")
        device.press("紧凑", "Compact")
        device.press("保存", "Save")
        deadline = time.monotonic() + 15
        while client.get("/user/reading-preferences").json()["theme"] != "compact":
            assert time.monotonic() < deadline, "全局样式未同步到服务器"
            time.sleep(0.2)
        device.press("阅读样式", "Reading style")
        device.press("专注", "Focus")
        device.screenshot("m1-style-preview")
        device.press("保存", "Save")
        deadline = time.monotonic() + 15
        while client.get(f"/notes/{note_id}").json()["display_overrides"].get("theme") != "focus":
            assert time.monotonic() < deadline, "单篇样式未同步到服务器"
            time.sleep(0.2)
        assert client.get("/user/reading-preferences").json()["theme"] == "compact"
        device.screenshot("m1-focus")
        device.press("阅读样式", "Reading style")
        reset = device.scroll_to("清除本文覆盖", "Reset to global style")
        device.screenshot("m1-before-reset")
        device.tap(reset)
        deadline = time.monotonic() + 15
        while any(
            value is not None
            for value in client.get(f"/notes/{note_id}").json()["display_overrides"].values()
        ):
            if time.monotonic() >= deadline:
                device.screenshot("m1-reset-failed")
                raise AssertionError("本文样式未重置")
            time.sleep(0.2)
        print("Android M1：平板横屏和系统大字体", flush=True)
        old_scale = (
            device.command("shell", "settings", "get", "system", "font_scale").decode().strip()
        )
        try:
            device.command("shell", "wm", "size", "1920x1200")
            device.command("shell", "wm", "density", "160")
            device.restart()
            device.press("Mobile acceptance")
            device.scroll_to("中文😀内容")
            tree = device.tree()
            assert any(
                n.get("text") in ("刷新", "Refresh") for n in tree.iter("node")
            ), "宽屏没有同时显示列表"
            device.screenshot("m1-tablet")
            device.command("shell", "settings", "put", "system", "font_scale", "2.0")
            time.sleep(1)
            device.scroll_to("中文😀内容")
            device.screenshot("m1-tablet-font-200")
            device.command("shell", "wm", "size", "reset")
            device.command("shell", "wm", "density", "reset")
            device.restart()
            device.press("Mobile acceptance")
            device.scroll_to("中文😀内容")
            device.screenshot("m1-phone-font-200")
        finally:
            device.command("shell", "wm", "size", "reset")
            device.command("shell", "wm", "density", "reset")
            device.command(
                "shell",
                "settings",
                "put",
                "system",
                "font_scale",
                old_scale if old_scale != "null" else "1.0",
            )
            device.restart()
            device.wait_text("Mobile acceptance")
        print("Android M1 阅读器专项通过", flush=True)
