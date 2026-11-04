# SPDX-License-Identifier: AGPL-3.0-or-later
"""在专用 Android 模拟器验收 M0；显式重置 App 数据，使用临时 API 和虚构笔记。"""

from __future__ import annotations

import argparse
import base64
import re
import sqlite3
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

from smoke_mobile import ROOT, temporary_api

PACKAGE = "app.clipo.android"


class Device:
    def __init__(self, adb: str, serial: str, output: Path) -> None:
        self.prefix = [adb, "-s", serial]
        self.output = output

    def command(self, *args: str, check: bool = True) -> bytes:
        result = subprocess.run(self.prefix + list(args), capture_output=True, timeout=40)
        if check and result.returncode:
            # 不将命令参数、输入内容或设备私有文件输出到日志。
            raise RuntimeError("ADB 命令执行失败，请检查指定模拟器的状态")
        return result.stdout

    def tree(self) -> ET.Element:
        self.command("shell", "rm", "-f", "/sdcard/clipo-smoke-window.xml")
        self.command(
            "shell", "uiautomator", "dump", "--compressed", "/sdcard/clipo-smoke-window.xml"
        )
        contents = self.command("exec-out", "cat", "/sdcard/clipo-smoke-window.xml", check=False)
        try:
            return ET.fromstring(contents)
        except ET.ParseError:
            # 冷启动/转场时无障碍树可能尚未就绪，由有时限的等待继续轮询。
            return ET.Element("hierarchy")

    def wait_text(self, *labels: str, contains: bool = False) -> ET.Element:
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            for node in self.tree().iter("node"):
                if (
                    node.get("text") in labels
                    or node.get("content-desc") in labels
                    or (contains and any(label in node.get("text", "") for label in labels))
                ):
                    return node
            time.sleep(0.3)
        raise AssertionError(f"界面未出现预期元素：{' / '.join(labels)}")

    def scroll_to(self, *labels: str) -> ET.Element:
        for _ in range(18):
            for node in self.tree().iter("node"):
                if any(label in node.get("text", "") for label in labels):
                    x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.attrib["bounds"]))
                    if x2 > x1 and y2 - y1 >= 8:
                        return node
            self.swipe(up=True)
        self.screenshot("failure-scroll")
        raise AssertionError(f"滚动后未找到元素：{labels}")

    def swipe(self, up: bool = True) -> None:
        size = self.command("shell", "wm", "size").decode()
        width, height = map(int, re.findall(r"(\d+)x(\d+)", size)[-1])
        x = str(int(width * 0.75))
        start, end = (0.75, 0.3) if up else (0.3, 0.75)
        self.command(
            "shell", "input", "swipe", x, str(int(height * start)), x, str(int(height * end)), "350"
        )

    def tap(self, node: ET.Element) -> None:
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.attrib["bounds"]))
        self.command("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))

    def press(self, *labels: str) -> None:
        self.tap(self.wait_text(*labels))

    def fill(self, index: int, value: str) -> None:
        fields = [
            n for n in self.tree().iter("node") if n.get("class") == "android.widget.EditText"
        ]
        self.tap(fields[index])
        self.command("shell", "input", "text", value)

    def screenshot(self, name: str) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / f"{name}.png").write_bytes(self.command("exec-out", "screencap", "-p"))

    def restart(self) -> None:
        self.command("shell", "am", "force-stop", PACKAGE)
        self.command("shell", "am", "start", "-n", f"{PACKAGE}/.MainActivity")

    def session_file(self) -> bytes:
        return self.command("exec-out", "run-as", PACKAGE, "cat", "shared_prefs/clipo_session.xml")

    def wait_rotation(self, previous: bytes) -> None:
        deadline = time.monotonic() + 20
        while self.session_file() == previous and time.monotonic() < deadline:
            time.sleep(0.2)
        assert self.session_file() != previous, "联网重启后未完成刷新凭据轮换"

    def verify_cleared(self) -> None:
        self.command("shell", "am", "force-stop", PACKAGE)
        preferences = ET.fromstring(self.session_file())
        assert preferences.find("string[@name='refresh']") is None, "退出后仍有刷新凭据"
        with tempfile.TemporaryDirectory(prefix="clipo-android-db-") as folder:
            database = Path(folder) / "clipo.db"
            for suffix in ("", "-wal", "-shm"):
                contents = self.command(
                    "exec-out", "run-as", PACKAGE, "cat", f"databases/clipo.db{suffix}", check=False
                )
                if contents:
                    Path(str(database) + suffix).write_bytes(contents)
            assert database.exists(), "未找到 Android 本地数据库"
            with sqlite3.connect(database) as connection:
                for table in ("account", "note", "note_detail", "operation", "sync_state"):
                    assert (
                        connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
                    ), f"退出后 {table} 未清空"
                assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def run(device: Device, apk: Path, reader: bool = False) -> None:
    if device.command("shell", "getprop", "ro.kernel.qemu").strip() != b"1":
        raise RuntimeError("此脚本仅允许在专用模拟器运行，不自动清理真机数据")
    if device.command("shell", "getprop", "sys.boot_completed").strip() != b"1":
        raise RuntimeError("请等待模拟器完成启动")
    device.command("install", "-r", str(apk))
    device.command("shell", "am", "force-stop", PACKAGE)
    assert device.command("shell", "pm", "clear", PACKAGE).strip() == b"Success"
    device.command("shell", "input", "keyevent", "KEYCODE_WAKEUP")
    device.command("shell", "wm", "dismiss-keyguard")
    with temporary_api(rich=reader) as base:
        port = f"tcp:{urlsplit(base).port}"
        device.command("reverse", port, port)
        try:
            print("Android：服务器检查与原生登录", flush=True)
            device.restart()
            device.wait_text("检查并继续", "Check and continue")
            device.fill(0, base)
            device.command("shell", "input", "keyevent", "KEYCODE_BACK")
            device.press("检查并继续", "Check and continue")
            device.wait_text("用户名", "Username")
            device.fill(0, "mobile-test")
            device.fill(1, "mobile-test-password")
            device.command("shell", "input", "keyevent", "KEYCODE_BACK")
            device.press("登录", "Sign in")
            device.wait_text("Mobile acceptance")
            device.screenshot("01-online-list")
            device.press("Mobile acceptance")
            device.scroll_to("中文😀内容")
            device.scroll_to("Offline reading.")
            device.screenshot("02-online-detail")

            if reader:
                from smoke_mobile_reader import verify_reader

                verify_reader(device, base)
            encrypted = device.session_file()
            assert b"mobile-test" not in encrypted and b"refresh_token" not in encrypted
            value = ET.fromstring(encrypted).findtext("string[@name='refresh']")
            assert value and len(base64.b64decode(value, validate=True)) > 28
            print("Android：进程重启与安全存储恢复", flush=True)
            device.restart()
            device.wait_text("Mobile acceptance")
            # Access token 仅在内存；联网重启应通过 Keystore 解密并轮换刷新令牌。
            device.wait_rotation(encrypted)

            print("Android：断开 API、强制停止后离线读取", flush=True)
            device.command("reverse", "--remove", port)
            device.restart()
            device.wait_text("Mobile acceptance")
            device.wait_text(
                "暂时无法刷新，已保留本地缓存。",
                "Unable to refresh. Your local cache is available.",
            )
            device.screenshot("03-offline-list")
            device.press("Mobile acceptance")
            device.scroll_to("中文😀内容")
            device.scroll_to("Offline reading.")
            device.wait_text(
                "暂时无法刷新，已保留本地缓存。",
                "Unable to refresh. Your local cache is available.",
            )
            device.screenshot("04-offline-detail")

            print("Android：恢复网络与退出清理", flush=True)
            offline_session = device.session_file()
            device.command("reverse", port, port)
            device.restart()
            device.wait_text("Mobile acceptance")
            device.wait_rotation(offline_session)
            device.press("刷新", "Refresh")
            device.wait_text("Mobile acceptance")
            device.press("退出登录", "Sign out")
            device.wait_text("退出登录并清理本地数据？", "Sign out and clear local data?")
            device.press("退出登录", "Sign out")
            device.wait_text("检查并继续", "Check and continue")
            device.screenshot("05-signed-out")
            device.verify_cleared()
            device.restart()
            device.wait_text("检查并继续", "Check and continue")
            print("Android M0 验收通过；截图：" + str(device.output), flush=True)
        finally:
            device.command("reverse", "--remove", port, check=False)
            device.command("shell", "am", "force-stop", PACKAGE, check=False)
            device.command("shell", "rm", "-f", "/sdcard/clipo-smoke-window.xml", check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reader", action="store_true", help="追加 M1 富文本、样式、平板和字体缩放验收"
    )
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", required=True, help="显式指定专用模拟器序列号")
    parser.add_argument(
        "--apk",
        type=Path,
        default=ROOT / "mobile/androidApp/build/outputs/apk/debug/androidApp-debug.apk",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "mobile/test-results/android-m0")
    parser.add_argument(
        "--reset-app-data", action="store_true", help="允许清除指定模拟器的 Clipo 缓存和登录"
    )
    args = parser.parse_args()
    if not args.reset_app_data:
        parser.error("此验收会清除 Clipo 测试数据，请使用专用模拟器并显式传入 --reset-app-data")
    if not args.apk.is_file():
        parser.error("APK 不存在，请先运行 :androidApp:assembleDebug")
    run(Device(args.adb, args.serial, args.output), args.apk.resolve(), args.reader)


if __name__ == "__main__":
    main()
