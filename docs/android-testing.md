# Android 模拟器连接与验收

## 本地 MuMu 连接记录

2026-09-21 在 Windows + WSL 环境验证：使用 MuMu 自带的 Windows ADB，从 WSL 调用即可连接，无需另装 Linux ADB 或进行无线配对。

| 项目 | 本机配置 |
| --- | --- |
| Windows ADB | `E:\Program Files\Netease\MuMu\nx_main\adb.exe` |
| WSL 调用路径 | `/mnt/e/Program Files/Netease/MuMu/nx_main/adb.exe` |
| Windows 本地连接地址 | `127.0.0.1:16384` |
| 模拟器内部地址 | `10.0.2.15` |
| Android 版本 | 15 |
| 设备型号 | `23113RKC6C` |
| 验证结果 | ADB 状态为 `device`，可执行 shell，`sys.boot_completed` 为 `1` |

先启动 MuMu 对应实例，再在 WSL Bash 执行：

```bash
CLIPO_ADB='/mnt/e/Program Files/Netease/MuMu/nx_main/adb.exe'
CLIPO_ANDROID_SERIAL='127.0.0.1:16384'

"$CLIPO_ADB" version
"$CLIPO_ADB" connect "$CLIPO_ANDROID_SERIAL"
"$CLIPO_ADB" devices -l
"$CLIPO_ADB" -s "$CLIPO_ANDROID_SERIAL" shell getprop ro.build.version.release
"$CLIPO_ADB" -s "$CLIPO_ANDROID_SERIAL" shell getprop sys.boot_completed
"$CLIPO_ADB" -s "$CLIPO_ANDROID_SERIAL" shell ip -4 addr show
```

预期连接结果为 `connected to 127.0.0.1:16384` 或 `already connected`。设备列表可能同时显示 `emulator-5554` 与 `127.0.0.1:16384`，本次两者指向同一个 MuMu 实例；后续命令显式使用 `-s 127.0.0.1:16384`，避免多设备歧义。

这里的 `127.0.0.1` 是 Windows ADB 访问的宿主机回环地址。`10.0.2.15` 是模拟器内部地址，无线配对窗口给出的动态端口不是本机已验证的直接连接入口。使用上述 MuMu 本地映射即可，不保存或复用临时配对码。

## 端口来源与排查

本机实例配置文件为：

```text
E:\Program Files\Netease\MuMu\vms\MuMuPlayer-15.0-0\MuMuPlayer-15.0-0.nemu
```

其中 `Forwarding name="ADB_PORT"` 配置为宿主机 `127.0.0.1:16384` 转发到模拟器 `5555`。可从 WSL 只读核对：

```bash
rg -n 'Forwarding.*ADB_PORT' \
  '/mnt/e/Program Files/Netease/MuMu/vms/MuMuPlayer-15.0-0/MuMuPlayer-15.0-0.nemu'
```

安装目录、实例编号或端口改变时，以当前实例的 MuMu 设置和映射配置为准，替换命令中的路径与设备地址。连接失败先检查实例是否启动、ADB 调试是否启用以及映射端口是否一致；本记录不要求编辑模拟器配置或重启所有 ADB 会话。

## 验证边界

本次只验证 ADB 连接与设备信息读取。尚未在 MuMu 验证 Clipo 页面访问、PWA 安装、Android 系统分享面板、登录后继续保存或完整采集流程。后续验收还需确认模拟器可访问 Clipo，以及页面满足 PWA 安装与分享入口的安全上下文要求。ADB 连接成功不能替代这些功能验收，也不能替代不同品牌手机的真机兼容性验证。

验收进度统一记录于 [构建进度](progress.md)；测试截图放在忽略目录 `frontend/test-results/`。
