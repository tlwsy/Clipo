# Clipo 原生移动端

按 [移动端计划](../docs/mobile-app-plan.md) 和 [移动端规格](../docs/mobile-app-spec.md) 实施。目前为 **M0 工程实现节点，里程碑验收尚未全部完成**。本次验证及限制见 [构建进度](../docs/progress.md)。

## 当前范围

- `shared/`：Kotlin Multiplatform 的 HTTP / 认证 / SQLDelight 缓存 / 笔记仓储 / 状态流；Android、iOS 和用于测试的 JVM target。
- `androidApp/`：Android 10+，Jetpack Compose + Material 3，服务器检查、登录、分页列表、纯文本详情、中英资源；Android 12+ 动态配色。
- `iosApp/`：iOS 18+，SwiftUI 同范围页面、Keychain、XcodeGen 工程描述与 XCTest；尚待 macOS 实际编译验证。
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

首次填写服务器**根地址**（也接受以 `/api/v1` 结尾的地址），确认规范化地址后输入账号密码。HTTP 自托管地址可用，登录页显示未加密提示；HTTPS 证书使用系统校验。拒绝 URL 内凭据、查询参数和片段，不跟随 HTTP 重定向；反向代理应填写最终可达地址。

本次安装的 Android SDK 在未跟踪的 `mobile/.local-tools/android-sdk/`，不进入 Git。系统默认 Java 25 不能用于这套 Gradle；本机可设置 `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64`。Gradle 缓存与下载代理只在本机任务环境配置，仓库不固定个人代理。

## 临时真实 API 联调

安装仓库后端依赖后，在根目录执行：

```bash
.venv/bin/python scripts/smoke_mobile.py
```

脚本用 `_env_file=None`、临时 SQLite/队列、随机密钥创建隔离服务器，直传虚构正文并创建标注，然后运行 `:shared:backendSmoke`。覆盖 JSON 登录、真实刷新轮换、笔记/详情/标注/阅读偏好反序列化、磁盘重开、离线读取和登出清理。所有临时进程和数据库退出时清理；不修改本机 Compose、已有账号或 `.env`，不请求采集站点与模型。

共享单测使用 MockEngine 和 SQLite 内存/临时文件驱动，覆盖刷新并发、失败分类、服务器地址、Retry-After 秒数/日期、账号和服务器切换、迟到响应、分页及删除隔离。JVM 结果不能替代 Android/iOS 安全存储与原生界面验收。

## iOS

需要 Apple Silicon Mac / macOS runner、JDK 21、Xcode 26.0.1、XcodeGen 与 SwiftLint。CI 固定 `macos-15` 上的 Xcode 26.0.1，版本来源见 [runner 镜像清单](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-arm64-Readme.md)。使用 [Kotlin 官方直接集成任务](https://kotlinlang.org/docs/multiplatform/multiplatform-direct-integration.html)构建共享 framework。

```bash
cd mobile/iosApp
brew install xcodegen swiftlint
xcodegen generate
swiftlint lint --strict
cd ..
xcodebuild -project iosApp/Clipo.xcodeproj -scheme Clipo -sdk iphoneos \
  -configuration Release CODE_SIGNING_ALLOWED=NO build
```

`Clipo.xcodeproj` 和 `Info.plist` 从 `project.yml` 生成，不手工编辑、不提交生成产物。CI 将 `.app` 放进 `Payload/` 并打包 `Clipo-unsigned.ipa`，只在构建成功后上传 `mobile-ios-unsigned` 工件；本次尚无经过验证的 IPA。签名/侧载和 iPhone 验收待后续完成。

## 数据与认证边界

- UI 从 SQLDelight 的 Flow 读取，网络仅通过 Repository 写库；读取失败保留缓存。401 刷新最终失败时清除令牌并回登录页，保留当前账号缓存；同账号重新登录可复用缓存。主动退出或换账号/服务器会清除旧代际。
- Access token 只在内存；刷新令牌和账号绑定元数据原子写入安全存储。Android 为 Keystore AES-GCM 加密的 SharedPreferences，并禁止云备份和设备迁移；iOS 为 `AfterFirstUnlockThisDeviceOnly` Keychain。HTTP 客户端不保存 Cookie，也不输出请求/响应正文。
- 并发 401 使用 Mutex 和已使用令牌比较，只轮换一次；所有结果落库前核对账号/服务器/代际。重试仅限一次认证续期，普通网络请求不自动重复。
- 本地 schema v1 包含 `account`、`note`、`note_detail`、`operation`、`sync_state`。笔记列表与完整详情采用生成 DTO 的 JSON 投影，保留标注、评论和阅读偏好；排序、代际及未来 `server_revision` / `deleted_at` 独立成列。空间、标签、标注的独立查询表随相应里程碑通过迁移新增，不将规划表误报为已实现。
- `operation` 只是 M3 的表结构预留，当前没有离线写入功能。`sync_state` 同样受代际约束。外键级联删除已通过 JVM SQLite 验证，双端平台驱动仍需设备验收。
- 当前是新建 v1 schema，尚无已发布旧版需要升级；未来增加 `.sqm` 迁移时须补充从 v1 升级及数据保留测试。生成的数据库快照只进入忽略的构建目录。

## 待验收

1. Android 模拟器/平板安装、真实原生登录、进程重启后的离线列表/详情、安全存储与截图。本次环境的 `/dev/kvm` 存在，但当前用户不在 `kvm` 组；已有 MuMu 端口未响应。启用权限或启动 MuMu 后继续，设备映射见 [Android 测试记录](../docs/android-testing.md)。
2. macOS CI 的 Swift/Kotlin Native 编译、XCTest、SwiftLint、IPA 打包，以及 iPhone 侧载。三个工作流仅完成本地定义和 YAML 检查，未执行远端 CI。
3. M0 所有验收项通过后再进入 M1；截图、CI 工件与实机结果写入 `docs/progress.md`，不能把 APK 构建或 JVM 联调当作真机通过。
