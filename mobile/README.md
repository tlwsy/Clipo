# Clipo 原生移动端

按 [移动端计划](../docs/mobile-app-plan.md) 和 [移动端规格](../docs/mobile-app-spec.md) 实施。**M0 工程、Android 模拟器与三条移动端 CI 已通过；双端实机验收尚未全部完成**。本次验证及限制见 [构建进度](../docs/progress.md)。

## 当前范围

- `shared/`：Kotlin Multiplatform 的 HTTP / 认证 / SQLDelight 缓存 / 笔记仓储 / 状态流；Android、iOS 和用于测试的 JVM target。
- `androidApp/`：Android 10+，Jetpack Compose + Material 3，服务器检查、登录、分页列表、纯文本详情、中英资源；Android 12+ 动态配色。
- `iosApp/`：iOS 18+，SwiftUI 同范围页面、Keychain、XcodeGen 工程描述与 XCTest；macOS CI 已通过编译、iOS 18.6 Keychain 测试、启动截图和未签名 IPA 打包。
- 三条独立 CI：共享测试、契约漂移与临时 API 联调；Android APK/lint；iOS 模拟器测试/SwiftLint/未签名 IPA。iOS 仅 PR 或手动触发，不随每次 push 运行。

M1 的原生富文本、阅读偏好、平板双栏，以及 M2–M5 的标注编辑、采集、离线写队列、预取、搜索、空间、回忆廊和质量打磨尚未实施。M0 可查看已经打开过的笔记详情缓存；最近 50 篇详情预取属于 M3。

## 构建

使用 JDK 21，Android SDK Platform 36 / Build Tools 35.0.0（AGP 默认版本），配置 `ANDROID_HOME` 或未提交的 `local.properties`。Gradle Wrapper 固定为 8.14.3 并校验官方 SHA-256；Kotlin 2.2.21、AGP 8.11.1、Ktor 3.3.1、SQLDelight 2.1.0 的版本见 `gradle/libs.versions.toml`。版本选择参考 [Kotlin 兼容表](https://kotlinlang.org/docs/multiplatform/multiplatform-compatibility-guide.html)。

```bash
# 从仓库根目录生成/检查移动端 DTO（不启动服务器、不读取部署密钥）
python3 scripts/generate_mobile_api.py
python3 scripts/generate_mobile_api.py --check

cd mobile
./gradlew :shared:jvmTest ktlintCheck
./gradlew :androidApp:assembleDebug :androidApp:lintDebug
```

APK：`mobile/androidApp/build/outputs/apk/debug/androidApp-debug.apk`。安装时显式指定设备：

```bash
adb -s emulator-5580 install -r mobile/androidApp/build/outputs/apk/debug/androidApp-debug.apk
```

本机包与 CI 包使用各自的调试签名，本次已核对证书指纹不同。跨来源覆盖安装若提示 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`，需先卸载旧测试包再安装；这会清理设备上的登录和缓存，服务端笔记保留。调试签名不作为正式发布签名。

首次填写服务器**根地址**（也接受以 `/api/v1` 结尾的地址），确认规范化地址后输入账号密码。HTTP 自托管地址可用，登录页显示未加密提示；HTTPS 证书使用系统校验。拒绝 URL 内凭据、查询参数和片段，不跟随 HTTP 重定向；反向代理应填写最终可达地址。

本次安装的 Android SDK 在未跟踪的 `mobile/.local-tools/android-sdk/`，不进入 Git。系统默认 Java 25 不能用于这套 Gradle；本机可设置 `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64`。Gradle 缓存与下载代理只在本机任务环境配置，仓库不固定个人代理。

## 临时真实 API 联调

安装仓库后端依赖后，在根目录执行：

```bash
.venv/bin/python scripts/smoke_mobile.py
```

脚本用 `_env_file=None`、临时 SQLite/队列、随机密钥创建隔离服务器，直传虚构正文并创建标注，然后运行 `:shared:backendSmoke`。覆盖 JSON 登录、真实刷新轮换、笔记/详情/标注/阅读偏好反序列化、磁盘重开、离线读取和登出清理。所有临时进程和数据库退出时清理；不修改本机 Compose、已有账号或 `.env`，不请求采集站点与模型。

共享单测使用 MockEngine 和 SQLite 内存/临时文件驱动，覆盖刷新并发、失败分类、服务器地址、Retry-After 秒数/日期、账号和服务器切换、迟到响应、分页及删除隔离。JVM 结果不能替代 Android/iOS 安全存储与原生界面验收。

## Android 原生界面验收

使用独立测试模拟器。脚本会安装 debug APK，清除该模拟器中 Clipo 的登录和缓存；必须显式传入 `--reset-app-data`，并拒绝在真机运行。已有日常测试实例应保留，另建 `clipo-m0-smoke`。

本机已创建 Android 15 / Pixel 6 测试实例，SDK 与 AVD 索引都放在忽略目录。用户加入 `kvm` 组后，重新登录或执行 `newgrp kvm`；已有进程也可以通过 `sg kvm -c '命令'` 使用新组权限。完整步骤见 [Android 测试说明](../docs/android-testing.md)。

```bash
# 仓库根目录；在具备 kvm 权限的终端启动专用模拟器
export ANDROID_HOME="$PWD/mobile/.local-tools/android-sdk"
export ANDROID_USER_HOME="$PWD/mobile/.local-tools/android-user"
export ANDROID_AVD_HOME="$ANDROID_USER_HOME/avd"
"$ANDROID_HOME/emulator/emulator" -avd clipo-m0-smoke -port 5582 \
  -no-window -no-audio -no-snapshot -gpu swiftshader_indirect -memory 2048
```

等 `adb -s emulator-5582 shell getprop sys.boot_completed` 返回 `1`，另开终端执行：

```bash
.venv/bin/python scripts/smoke_mobile_android.py \
  --adb "$PWD/mobile/.local-tools/android-sdk/platform-tools/adb" \
  --serial emulator-5582 --reset-app-data
```

脚本复用临时 API 夹具，使用 UI Automator 操作真实 Compose 页面：检查服务器、登录、列表及中文/emoji 正文、进程重启后的 Keystore 解密及刷新轮换、断开 API 转发后的列表/详情缓存、联网恢复、退出后 SQLite 五张表及加密凭据清理。退出时移除本次随机端口转发、停止测试 App 并清理临时 API；不调用真实平台或模型。截图保存在忽略的 `mobile/test-results/android-m0/`，不提交到 Git。模拟器结果不替代平板/iPhone 实机验收。

## iOS

需要 Apple Silicon Mac / macOS runner、JDK 21、Xcode 26.0.1、XcodeGen 与 SwiftLint。CI 固定 `macos-15` 上的 Xcode 26.0.1，版本来源见 [runner 镜像清单](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-arm64-Readme.md)。使用 [Kotlin 官方直接集成任务](https://kotlinlang.org/docs/multiplatform/multiplatform-direct-integration.html)构建共享 framework。

CI 的 M0 运行基线为 iPhone 16 / iOS 18.6；Xcode 26.0.1 编译，模拟器包使用本地临时签名，真机 IPA 保持未签名。编译、显式开机、串行 XCTest 与截图分步执行，并设置超时。首次 iOS 26 模拟器运行在编译/链接完成后卡在测试宿主启动，取消后保留了诊断工件；参考 [runner 同类问题](https://github.com/actions/runner-images/issues/13264)，改用受支持的 18.6 运行基线。iOS 26 的运行和 Liquid Glass 验证仍需独立完成，不能由 18.6 结果替代。

```bash
cd mobile/iosApp
brew install xcodegen swiftlint
xcodegen generate
swiftlint lint --strict
cd ..
xcodebuild -project iosApp/Clipo.xcodeproj -scheme Clipo -sdk iphoneos \
  -configuration Release CODE_SIGNING_ALLOWED=NO build
```

`Clipo.xcodeproj` 和 `Info.plist` 从 `project.yml` 生成，不手工编辑、不提交生成产物。CI 将 `.app` 放进 `Payload/` 并打包 `Clipo-unsigned.ipa`，只在构建成功后上传 `mobile-ios-unsigned` 工件。

2026-11-04，代码提交 `7dfa3c7` 的 [iOS CI](https://github.com/tlwsy/Clipo/actions/runs/41804775435) 已通过：SwiftLint、Kotlin/Native 与 Swift 编译、iPhone 16 / iOS 18.6 的 **1 项** Keychain 读写/轮换/删除 XCTest、原生服务器页启动截图及未签名 IPA 打包。[IPA 工件](https://github.com/tlwsy/Clipo/actions/runs/41804775435/artifacts/13310885639) 已下载至本机忽略目录 `mobile/test-results/ci-ios-7dfa3c7/Clipo-unsigned.ipa`；核对包标识 `app.clipo.ios`、最低 iOS 18.0、ARM64 真机平台与未签名状态通过。该包仍需用户签名侧载，当前测试未覆盖 iOS 原生登录、真实服务器笔记或离线重启，这些需在 iPhone 补齐。

## 数据与认证边界

- UI 从 SQLDelight 的 Flow 读取，网络仅通过 Repository 写库；读取失败保留缓存。401 刷新最终失败时清除令牌并回登录页，保留当前账号缓存；同账号重新登录可复用缓存。主动退出或换账号/服务器会清除旧代际。
- Access token 只在内存；刷新令牌和账号绑定元数据原子写入安全存储。Android 为 Keystore AES-GCM 加密的 SharedPreferences，并禁止云备份和设备迁移；iOS 为 `AfterFirstUnlockThisDeviceOnly` Keychain。HTTP 客户端不保存 Cookie，也不输出请求/响应正文。
- 并发 401 使用 Mutex 和已使用令牌比较，只轮换一次；所有结果落库前核对账号/服务器/代际。重试仅限一次认证续期，普通网络请求不自动重复。
- 本地 schema v1 包含 `account`、`note`、`note_detail`、`operation`、`sync_state`。笔记列表与完整详情采用生成 DTO 的 JSON 投影，保留标注、评论和阅读偏好；排序、代际及未来 `server_revision` / `deleted_at` 独立成列。空间、标签、标注的独立查询表随相应里程碑通过迁移新增，不将规划表误报为已实现。
- `operation` 只是 M3 的表结构预留，当前没有离线写入功能。`sync_state` 同样受代际约束。外键级联删除已通过 JVM SQLite 验证，双端平台驱动仍需设备验收。
- 当前是新建 v1 schema，尚无已发布旧版需要升级；未来增加 `.sqm` 迁移时须补充从 v1 升级及数据保留测试。生成的数据库快照只进入忽略的构建目录。

## 待验收

1. Android 平板实机验收。2026-11-04 用户已确认完成模拟器上的 App 测试；本机 `kvm` 组已包含当前用户，`-accel-check` 通过。可复现的 Android 原生验收及结果见上节和 [构建进度](../docs/progress.md)，不再以 KVM 权限作为阻塞。
2. iPhone 签名侧载、真实服务器登录/列表/详情、进程重启后的离线读取、退出及换账号，以及 iOS 26 运行。三条移动端 CI 和既有全仓库 CI 已在 `7dfa3c7` 通过；iOS CI 的 18.6 Keychain 测试与服务器页截图只覆盖上述实际范围。
3. M0 所有验收项通过后再进入 M1；截图、CI 工件与实机结果写入 `docs/progress.md`，不能把 APK 构建或 JVM 联调当作真机通过。
