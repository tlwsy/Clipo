# Clipo 移动端计划

**版本**: 1.0
**日期**: 2026-11-04
**状态**: M1 阅读器已实现，Android 与 iOS 18.6 自动验证通过；双端实机及 iOS 26 运行仍待验收
**配套文档**: [移动端规格](mobile-app-spec.md)（功能与技术细节）

当前工程、命令和实现边界见 [mobile/README.md](../mobile/README.md)，本次实际验证见 [构建进度](progress.md)。以下里程碑继续作为验收目标，不表示已经全部实现。

---

## 1. 目标与边界

### 目标

1. 为 Clipo 提供 iOS 与 Android 客户端，交互与系统控件按各平台原生方式实现：Android 使用 Jetpack Compose + Material Design 3，iOS 使用 SwiftUI，并在 iOS 26+ 采用 Liquid Glass。
2. 覆盖从骨架到可日用的完整路径：登录、笔记列表、阅读器、标注、采集、搜索、空间、回忆廊。
3. 业务逻辑、数据模型、本地数据库、离线队列、同步引擎一次实现，双端共享（Kotlin Multiplatform）。
4. 数据层从第一天按"本地优先"设计，为第二阶段"本机为核心 + 第三方云同步"预留，不推翻重来。

### 非目标（本阶段明确不做）

- 不上架 App Store / Google Play，不做应用内付费；发布策略留待实际效果评估后决定。
- 不做 WebView 套壳，不以"能打开网页"为验收标准。
- 不改动现有后端架构；App 通过既有 REST API（`/api/v1`）接入。
- 不在首版实现完整独立版（App 不依赖任何服务器）：网页抓取与 AI 摘要仍依赖 Clipo 服务端。
- 不做服务端推送（APNs / FCM / ntfy）；首版仅本地通知。
- 不迁移在线字体库（Fontsource 动态下载）到移动端；改用内置精选字体。

---

## 2. 已确认决策

| 编号 | 决策 | 结论 |
| --- | --- | --- |
| D1 | 开发方式 | 全部由 AI 编写，用户每日抽空验收，不设固定工期 |
| D2 | 原生验收标准 | 方案 B：交互与系统能力全部原生，允许品牌化视觉 |
| D3 | 技术路线 | KMP 共享逻辑 + Jetpack Compose / SwiftUI 双原生 UI |
| D4 | 首版范围 | 采集、笔记、阅读器+标注、搜索、空间、回忆廊、登录/设置 |
| D5 | 数据模式 | 模式 A（连服务器 + 本地缓存/离线队列）先行；模式 B（本地优先 + 云同步）仅预留架构 |
| D6 | 登录 | 账号密码登录，refresh token 存 Keychain / Android Keystore；配对码作为后续补充 |
| D7 | 系统下限 | iOS 18+（Liquid Glass 在 iOS 26+ 渐增强），Android 10（API 29）+, Material 3 动态取色 |
| D8 | 推送 | 首版仅本地通知；自托管推送列为设置方向 |
| D9 | 推进顺序 | 先 Android（平板真机 + 模拟器 + CI），后 iOS（CI 出未签名 ipa，侧载验证） |
| D10 | 仓库结构 | 同仓库新增 `mobile/`，内分 `shared/`、`androidApp/`、`iosApp/` |
| D11 | 跨端一致性 | Repository / UseCase / 状态流共享；ViewModel 允许各端薄包装；"行为一致"优先于"代码一致" |
| D12 | 本地数据库 | SQLDelight（两端共用，SQL 优先） |
| D13 | 阅读偏好 | 完整承接服务端偏好与单篇覆盖；在线字体改为内置精选字体 |
| D14 | 界面语言 | 中英双语字符串资源，默认中文 |

---

## 3. 架构总览

```text
┌──────────────────────────────────────────────────────────────┐
│                       mobile/ (Kotlin Multiplatform)         │
│                                                              │
│  shared/                                                     │
│   ├─ api/        Ktor 客户端、错误映射、认证拦截、幂等键       │
│   ├─ auth/       登录/刷新令牌轮换、安全存储抽象、服务器配置    │
│   ├─ db/         SQLDelight schema、DAO、迁移                  │
│   ├─ repo/       笔记/标注/空间/搜索/回忆廊/任务 Repository     │
│   ├─ sync/       离线队列重放、预取、账号代际校验              │
│   ├─ reading/    阅读偏好模型、HCT 取色、块索引与 UTF-16 偏移   │
│   └─ model/      与 openapi 契约对齐的 DTO                     │
│                                                              │
│  androidApp/     Jetpack Compose · Material 3 · Navigation     │
│  iosApp/         SwiftUI · Liquid Glass · NavigationStack      │
└──────────────────────────────────────────────────────────────┘
                              │ HTTPS / JSON
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ FastAPI /api/v1 · JWT + refresh 轮换 · 现有 REST 契约          │
└──────────────────────────────────────────────────────────────┘
```

关键原则：

- **共享层不碰 UI**：不共享 Composable / SwiftUI 视图，不做跨平台自绘。
- **本地数据库是所有读取的单一数据源**：UI 永远从 SQLDelight 读，网络写入先落库再刷新，离线与在线走同一条渲染路径。
- **在写模式 A 的同步层时，就按模式 B 的约束设计**：每条本地记录带 `owner`、`generation`、`server_revision`（预留），所有写操作走幂等键队列，未来接入 WebDAV / iCloud 同步时只替换传输层。

---

## 4. 数据模式

### 模式 A：服务器为核心（首版交付）

- 内容、标注、偏好、空间存储在用户自托管的 Clipo 服务器。
- App 缓存最近笔记完整详情（含正文块、标注、评论、摘要）与全量列表投影。
- 收藏、删除、提交链接支持离线排队，恢复网络后按原顺序重放；与网页端现有语义一致。
- 网页端与 App 可同时使用，服务端是唯一事实来源。

### 模式 B：本机为核心（仅架构预留）

- 内容与 AI 能力在设备本地完成，第三方云（WebDAV / iCloud / 自建）仅做同步。
- 需求拆解与风险见规格文档第 13 节；本计划不排期、不实现，仅保证模式 A 不阻碍它。

---

## 5. 里程碑

进度按"骨架 → 可用 → 真正好用"三档推进，每个里程碑结束产出双端截图或录屏、测试报告，并写入 [构建进度](progress.md)。

### 骨架（Skeleton）

**M0 · 工程底座**（约 1–2 周当量，AI 连续作业）

- 建立 `mobile/` Gradle 多模块工程；KMP 版本目录（libs.versions.toml）；SQLDelight、Ktor、序列化依赖。
- CI 三条流水线可运行；Android debug 包可安装；iOS 未签名 ipa 可从 CI 下载。
- 共享层：API 客户端、错误模型、token 存储抽象、SQLDelight schema 初版、笔记列表/详情 Repository。
- 双端：服务器地址页、登录页、笔记列表（只读）、笔记详情（纯文本渲染）。
- 验收：登录后能看到服务器上的真实笔记；断网重开显示缓存列表；CI 全绿。

**M1 · 阅读器原生化**

- Android：Material 3 列表 + 详情，平板双栏（NavigationRail + 列表 + 阅读区），edge-to-edge，预测性返回。
- iOS：SwiftUI NavigationStack + TabView，iOS 26 Liquid Glass 工具栏，旧系统材质回退。
- 阅读样式承接：主题预设、背景/文字色、字体、字号、行高、段距、对齐、宽度、单篇覆盖。
- 验收：同一篇笔记在网页与两端视觉语义一致；平板横屏双栏可用；系统字体缩放不破版。

### 可用（Usable）

**M2 · 标注与交互**

- 四色高亮 + 批注；侧栏列表、跳回原文、编辑与删除。
- 块索引与 UTF-16 偏移严格对齐网页语义（见规格第 9 节）。
- 双端选择工具栏用平台原生组件；iOS 用 UITextView 内核保证 `NSRange` 与偏移一致。
- 验收：网页创建的标注在 App 正确高亮并可编辑；App 创建的标注网页可见。

**M3 · 采集与离线**

- 系统分享：Android `ACTION_SEND` 过滤器；iOS Share Extension + App Group 队列。
- App 内粘贴链接采集；任务列表与状态轮询；失败重试。
- 离线队列：收藏、删除、提交链接；预取最近 50 篇；离线状态条与重试入口。
- 本地通知：采集完成、摘要完成（App 运行期间）。
- 验收：从 B 站/小红书分享到 Clipo 成功入库；飞行模式下收藏、恢复网络自动同步。

**M4 · 搜索、空间与回忆廊**

- 全文/语义搜索、高亮命中、筛选（标签/收藏/空间）。
- 空间创建、编辑、增删笔记、颜色与图标。
- 回忆廊全屏卡片、阅读计时上报、忽略操作。
- 验收：搜索结果与网页一致；大规模笔记下平板滚动流畅。

### 真正好用（Genuinely good）

**M5 · 打磨与质量门**

- 空状态、错误状态、加载骨架屏、重试路径全覆盖；离线优先首屏。
- 无障碍：TalkBack / VoiceOver、动态字体、减少动态效果、对比度。
- 性能：冷启动 < 2s，列表 60fps，大文档滚动无卡顿；内存与图片加载优化。
- 动效：平台原生手势、触觉反馈、过渡动画；不做跨平台统一动效。
- 设置：账号、服务器切换、缓存管理、通知开关、关于。
- 验收：规格第 12 节验收清单全部通过；用户连续一周日常使用无阻断问题。

---

## 6. 验证链路

| 目标 | 方式 | 说明 |
| --- | --- | --- |
| 共享层正确性 | JVM 单测（MockEngine + SQLDelight 内存驱动） | 每次 push |
| Android 快速验证 | WSL2 内 Android 模拟器（`/dev/kvm` 已确认可用） | SDK 已安装，M0 原生验收通过 |
| Android 真机 | 安卓平板，adb 安装 debug apk | 主要验收设备 |
| iOS 构建 | GitHub Actions macOS runner，产出未签名 ipa | 本机 WSL2 无法编译 Swift |
| iOS 真机 | iPhone + AltStore / Sideloadly 侧载 | 免费签名每 7 天重签，最多 3 个 App，无 APNs |
| 契约一致性 | `make gen-api` 后对比 `frontend/openapi.json` | 与网页端共用契约 |

当前已复核的环境事实：WSL2 提供 `/dev/kvm`，`kvm` 组包含当前用户，加速检测与实际模拟器启动通过；SDK、平台工具和 Android 15 系统镜像已安装在仓库忽略目录。原生验收命令见 [移动端工程说明](../mobile/README.md)。

2026-11-04 实施初次核对：沙箱外 `/dev/kvm` 存在，但当时账户 **不在 `kvm` 组**，sudo 需要交互认证；MuMu 已记录端口未响应，规划时的权限假设不成立。当时完成了 SDK 和任务专用模拟器镜像安装、Android 编译，设备验收等待权限配置。

2026-11-04 后续更新：用户完成组权限配置并确认已测试模拟器 App。实际 `kvm` 组现已包含当前用户，经 `sg kvm` 启动的加速检测通过，Android 15 专用验收模拟器成功开机；不再被 KVM 阻塞。保留用户实例，独立自动验收实例及脚本见 [Android 测试说明](android-testing.md)，本次结果见 [构建进度](progress.md)。

---

## 7. CI 设计

新增三条 workflow，不修改现有 `ci.yml` 的行为：

| 文件 | 触发 | 内容 |
| --- | --- | --- |
| `.github/workflows/mobile-shared.yml` | `mobile/**` 变更 | 共享层单测、`ktlint` / `detekt` |
| `.github/workflows/mobile-android.yml` | `mobile/**` 变更 | `assembleDebug`、上传 apk 工件；可选模拟器仪器测试 |
| `.github/workflows/mobile-ios.yml` | `mobile/**` 变更或手动 | macOS runner：`xcodebuild` 未签名 ipa、单元测试、SwiftLint |

原则：三条相互独立，失败能直接定位平台；iOS 流水线允许手动触发，避免每次提交占用 macOS 额度。

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| iOS 构建链路长、反馈慢 | 迭代效率低 | 先 Android 打通共享层与契约；iOS 只做 UI 层，减少往返 |
| 双端交互语义漂移 | "行为不一致" | 状态与 UseCase 在共享层收敛；UI 状态机用契约测试固定 |
| 标注偏移在不同渲染器下错位 | 高亮错位、批注错字 | iOS 用 UITextView，Android 用自定义文本渲染；共享层统一 UTF-16 与块索引算法并做黄金用例 |
| 大文档与图片列表性能 | 卡顿、OOM | 分块懒加载、图片异步解码、列表用稳定键；性能门作为 M5 阻断项 |
| 免费 iOS 签名限制 | 无法推送、7 天重签 | 首版不依赖推送；文档写明重签流程 |
| 服务端 API 为网页设计 | 移动端请求次数多 | 预取合并、缓存优先；必要时与网页端一起演进接口，但不破坏兼容 |
| AI 编写代码质量 | 隐性缺陷 | 每个里程碑设测试门；共享层高覆盖单测；真机验收不可省略 |

---

## 9. 交付物清单

- `docs/mobile-app-plan.md`（本文档）
- `docs/mobile-app-spec.md`（规格：产物、架构、数据、界面、验收）
- 后续里程碑产出：`mobile/` 工程、CI 工作流、构建进度记录、双端截图

---

## 10. 待用户确认的后续事项

1. Android SDK 与模拟器已搭建并验收，接续安卓平板实机验证。
2. iOS 侧载工具选择（AltStore 或 Sideloadly）与 Apple ID 签名方式。
3. M3 完成后决定是否启动模式 B 的需求拆解。
