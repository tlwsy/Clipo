# Android 模拟器连接与验收

## 原生 App：WSL KVM 与独立验收实例

2026-11-04 用户完成 KVM 配置并确认已进行模拟器 App 测试。本次重新检查 `/dev/kvm` 为 `root:kvm`、权限 `0660`，`kvm` 组包含 `tlwsy`；通过 `sg kvm -c '.../emulator -accel-check'` 实际得到 `KVM (version 12) is installed and usable`。

尚未加入组时，在自己的 WSL 终端执行：

```bash
sudo usermod -aG kvm "$USER"
newgrp kvm
```

`newgrp` 开启新 shell；已有 Codex/终端进程的附加组不会自动刷新，可重新登录或用 `sg kvm -c '命令'` 启动模拟器。无需修改设备节点为全员可写。

SDK 安装在仓库忽略目录 `mobile/.local-tools/android-sdk/`。保留用户原来的 `clipo-m0` 实例，新增 `clipo-m0-smoke` 用于会清理 App 数据的自动验收；索引在 `mobile/.local-tools/android-user/avd/`，数据在 `mobile/.local-tools/avd/clipo-m0-smoke.avd/`。新环境可在仓库根目录创建同名实例：

```bash
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME="$PWD/mobile/.local-tools/android-sdk"
export ANDROID_USER_HOME="$PWD/mobile/.local-tools/android-user"
"$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" create avd \
  --name clipo-m0-smoke --package 'system-images;android-35;google_apis;x86_64' \
  --device pixel_6 --path "$PWD/mobile/.local-tools/avd/clipo-m0-smoke.avd"
```

命令要求已安装上述 SDK 系统镜像；实例已存在时直接复用，不强制覆盖。启动及原生验收脚本见 [移动端工程说明](../mobile/README.md#android-原生界面验收)。脚本显式指定 `emulator-5582`，使用临时 FastAPI 和随机端口反向转发，避免读取日常账号、部署密钥或真实笔记。

手动测试本机 Compose 时，安装 debug APK 后执行 `adb -s <设备序列号> reverse tcp:18000 tcp:18000`，App 填写 `http://127.0.0.1:18000`；ADB 服务所在宿主机必须能访问该端口。离线验证应移除该转发（`reverse --remove tcp:18000`），强制停止并重新打开 App；仅开启飞行模式不能保证 USB 端口转发断开。Android 真机不需要 KVM，使用设备所属宿主机的 ADB，开启 USB 调试并在设备上授权后显式选择序列号；Windows ADB 安装 APK 时使用 Windows 可访问的路径。

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
