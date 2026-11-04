# Clipo 移动端规格

**版本**: 1.0
**日期**: 2026-11-04
**状态**: M0 工程、Android 模拟器与 CI 已通过，实机验收待完成；当前范围与边界见 [工程说明](../mobile/README.md)
**上层文档**: [移动端计划](mobile-app-plan.md)

本规格定义从工程骨架到"真正好用"的完整技术契约：目录结构、共享层、数据库、认证、同步、逐屏规格、标注语义、验收标准。

---

## 1. 仓库与产物

```text
mobile/
├── settings.gradle.kts
├── gradle/libs.versions.toml          # 版本目录（Kotlin、Compose、Ktor、SQLDelight…）
├── build.gradle.kts
├── gradle.properties
├── shared/                            # Kotlin Multiplatform
│   └── src/
│       ├── commonMain/kotlin/...      # api / auth / db / repo / sync / reading / model
│       ├── commonMain/sqldelight/     # .sq 文件
│       ├── commonTest/kotlin/...      # 共享单测（MockEngine、内存数据库）
│       ├── androidMain/kotlin/...     # Keystore、OkHttp 引擎、通知
│       └── iosMain/kotlin/...         # Keychain、Darwin 引擎
├── androidApp/                        # Jetpack Compose
└── iosApp/                            # SwiftUI + Xcode 工程（由 CI 构建）
```

产物：

| 产物 | 位置 | 用途 |
| --- | --- | --- |
| Debug apk | CI 工件 `mobile-android-debug` | 平板与模拟器安装 |
| 未签名 ipa | CI 工件 `mobile-ios-unsigned` | AltStore / Sideloadly 侧载 |
| 共享层测试报告 | CI 日志 | 每次评审的回归证据 |
| 契约漂移检查 | CI 步骤 | `shared` 中 DTO 与 `frontend/openapi.json` 对齐 |

现有 `frontend/`、`backend/`、`extension/`、`Dockerfile`、`docker-compose.yml` 不做结构性修改。

---

## 2. 共享层模块

| 包 | 职责 | 关键约束 |
| --- | --- | --- |
| `api` | HTTP 客户端（Ktor + ContentNegotiation JSON）、`{error:{code,message,detail}}` 映射、`Retry-After` 解析、超时 | 不持有 UI 状态；不做全局重试风暴 |
| `auth` | 登录、刷新轮换、登出、`auth/me`、服务器地址管理 | refresh token 只进安全存储；access token 只在内存 |
| `db` | SQLDelight schema、DAO、迁移 | 所有读取从本地库；写入先落库 |
| `repo` | 笔记、标注、空间、搜索、回忆廊、任务、设置的领域接口 | 输入输出为 DTO/领域模型，不发原 HTTP 结构 |
| `sync` | 离线队列重放、预取、代际校验、在线状态 | 与网页 `lib/offline-sync.ts` 语义对齐 |
| `reading` | 阅读偏好、颜色解析、块索引与偏移、字体映射 | 黄金用例覆盖 UTF-16 与块编号 |
| `model` | 与 openapi 契约对齐的 DTO（kotlinx.serialization） | 字段名与 `frontend/openapi.json` 一致 |

约定：

- 每个 Repository 返回 `Result` 风格的类型（成功 / 可重试错误 / 认证错误 / 永久错误），UI 层不解析 HTTP 状态码。
- UseCase 是纯 Kotlin 协程函数；状态流用 `StateFlow` / `SharedFlow` 暴露给双端。
- Composable 与 SwiftUI View 永远不直接调用 `api` 包，只通过 Repository / UseCase。

---

## 3. 本地数据库（SQLDelight）

### 3.1 表结构（初版）

```sql
-- 账号与安全元数据（不含密码/令牌，令牌在安全存储）
CREATE TABLE account (
  server_id      TEXT NOT NULL,      -- 规范化服务器基址
  user_id        INTEGER NOT NULL,
  username       TEXT NOT NULL,
  email          TEXT NOT NULL,
  generation     TEXT NOT NULL,      -- 每次切换账号/服务器重新生成
  PRIMARY KEY (server_id, user_id)
);

-- 笔记列表投影（对应 NoteItem）
CREATE TABLE note (
  id             INTEGER NOT NULL,
  generation     TEXT NOT NULL,
  title          TEXT NOT NULL,
  url            TEXT NOT NULL,
  platform       TEXT NOT NULL,
  site_name      TEXT,
  author         TEXT,
  summary_excerpt TEXT NOT NULL,
  status         TEXT NOT NULL,      -- ready | original_only
  created_at     TEXT NOT NULL,
  is_favorite    INTEGER NOT NULL DEFAULT 0,
  cached_at      TEXT,
  PRIMARY KEY (generation, id)
);

-- 笔记详情（对应 NoteResponse 中非列表字段）
CREATE TABLE note_detail (
  id             INTEGER NOT NULL,
  generation     TEXT NOT NULL,
  content_json   TEXT NOT NULL,      -- CapturedContent（含 blocks）
  summary_markdown TEXT,
  key_points_json TEXT NOT NULL,
  suggested_tags_json TEXT NOT NULL,
  comment_insights_json TEXT NOT NULL,
  reading_preferences_json TEXT NOT NULL,
  display_overrides_json TEXT NOT NULL,
  summary_error  TEXT,
  updated_at     TEXT NOT NULL,
  PRIMARY KEY (generation, id)
);

CREATE TABLE tag (
  id INTEGER NOT NULL, generation TEXT NOT NULL, name TEXT NOT NULL,
  PRIMARY KEY (generation, id)
);
CREATE TABLE note_tag (
  note_id INTEGER NOT NULL, tag_id INTEGER NOT NULL, generation TEXT NOT NULL,
  PRIMARY KEY (generation, note_id, tag_id)
);
CREATE TABLE collection_row (
  id INTEGER NOT NULL, generation TEXT NOT NULL,
  name TEXT NOT NULL, color TEXT NOT NULL, icon TEXT,
  note_count INTEGER NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (generation, id)
);
CREATE TABLE collection_note (
  collection_id INTEGER NOT NULL, note_id INTEGER NOT NULL, generation TEXT NOT NULL,
  PRIMARY KEY (generation, collection_id, note_id)
);
CREATE TABLE annotation (
  id INTEGER NOT NULL, note_id INTEGER NOT NULL, generation TEXT NOT NULL,
  block_index INTEGER NOT NULL, start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL,
  selected_text TEXT NOT NULL, highlight_color TEXT, note_text TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (generation, id)
);

-- 离线写队列
CREATE TABLE operation (
  id             TEXT PRIMARY KEY,   -- 幂等键（客户端生成 UUID）
  generation     TEXT NOT NULL,
  position       INTEGER NOT NULL,   -- 重放顺序
  created_at     TEXT NOT NULL,
  path           TEXT NOT NULL,
  method         TEXT NOT NULL,      -- POST | PATCH | DELETE
  body           TEXT,
  error          TEXT
);

-- 同步游标与预取状态
CREATE TABLE sync_state (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
```

### 3.2 迁移策略

- 每个 schema 版本一个 `.sqm` 文件；CI 跑迁移测试（从 v1 升级到最新）。
- 账号切换：删除旧 `generation` 全部数据；不保留跨账号缓存。

---

## 4. 认证

### 4.1 流程

```text
设置服务器 URL → GET /meta/version（确认可达与 setup_completed）
→ POST /auth/login {username,password}
→ 保存 refresh_token 到安全存储，内存持有 access_token
→ 后续请求 Authorization: Bearer <access_token>
→ 401 时：POST /auth/refresh {"refresh_token":"..."}（轮换，旧 token 立即失效）
→ refresh 失败：清除安全存储，回到登录页
```

- 安全存储：iOS 用 Keychain（`kSecAttrAccessibleAfterFirstUnlock`），Android 用 Keystore 加密的 DataStore（或 `EncryptedSharedPreferences`）。
- **刷新并发防护**：共享层用 Mutex 保证同一时刻只有一个刷新请求，避免旧 token 轮换后被另一个请求重复使用导致登出风暴。
- 登出：调用 `POST /auth/logout`（传 refresh_token），然后清除本地会话与缓存。
- 现有后端即返回 `refresh_token` 且 `/auth/refresh` 接受 JSON 中的 `refresh_token`，App 首版**无需新增后端接口**；配对码登录列为后续补强。
- 服务器地址校验：拒绝非 http/https、拒绝 URL 中带凭据；显示规范化后地址供用户确认。

### 4.2 请求附加约定

- `Idempotency-Key`：所有写操作由客户端生成并复用（离线重放同一 key），与网页 `offline-store.ts` 语义一致。
- 服务器版本：登录后保存 `/meta/version` 返回的 `version`，设置页展示；不强制最低版本，但遇到契约不兼容字段时降级渲染并提示升级。

---

## 5. 数据流与同步

### 5.1 读取路径

```text
UI 订阅 DB 查询（Flow）→ 网络后台刷新 → 写入 DB → UI 自动更新
```

- 首屏永远先出缓存；网络刷新不阻塞渲染。
- 笔记详情：先返回本地 `note_detail`（可能来自预取），再按需请求 `GET /notes/{id}`。
- 图片：正文 `blocks.type == "image"` 仍为原站外链，使用平台图片加载器缓存；不下载视频。

### 5.2 写入路径

| 操作 | 在线 | 离线 |
| --- | --- | --- |
| 收藏/取消收藏 | `PATCH /notes/{id}` `{is_favorite}` | 入队 `PATCH` |
| 删除笔记 | `DELETE /notes/{id}` | 入队 `DELETE` |
| 提交链接采集 | `POST /captures` | 入队 `POST` |
| 标注增删改 | 直接请求 | 首版不支持离线（与网页一致）；UI 禁用并提示 |
| 空间编辑、阅读样式 | 直接请求 | 首版不支持离线 |

### 5.3 重放协议（对齐网页语义）

1. 在线才重放；同一时刻只有一个重放任务（Mutex）。
2. 重放前 `GET /auth/me`，账号 ID 与用户名必须一致，`generation` 必须匹配；否则停止。
3. 按 `position` 顺序执行；使用原 `Idempotency-Key`。
4. `DELETE` 返回 404 视为成功。
5. 401 停止重放并保留队列（等待用户重新登录）。
6. 其他失败记录 `error` 并停止后续操作，UI 显示失败原因与"重试 / 取消失败操作"。
7. 成功后删除 `operation` 行；全部清空后发出 `synced` 事件。

### 5.4 预取

- 登录或打开应用后拉取 `GET /notes?limit=50`，并发 4 拉取详情并落库（与网页 `prefetchNotes` 一致）。
- 预取不覆盖用户正在编辑的标注/样式草稿；只更新服务器字段。
- 后台刷新用 `updated_at` 增量判断，不做轮询风暴：前台每 60 秒一次，后台按系统调度。

---

## 6. 逐屏规格

### 6.1 启动与服务器配置

| 项 | Android | iOS |
| --- | --- | --- |
| 首次启动 | 引导页：填写 Clipo 服务器地址，校验 `/meta/version` | 同左，使用 Form/Section |
| 已配置 | 直接进入（有缓存）或后台刷新 | 同左 |
| 切换服务器 | 设置 > 服务器，需明确确认并清理缓存 | 同左 |

### 6.2 登录

- 字段：用户名、密码；错误映射 `invalid_credentials` 等中文 message 直接展示。
- 生物识别解锁（可选，M5）：iOS Face ID / Touch ID；Android BiometricPrompt。会话在锁屏后保护，不影响后台重放。

### 6.3 笔记列表

- 数据：`GET /notes?cursor&limit&tag_id&favorite&collection_id&q`，游标分页。
- 卡片：标题、平台/站点、作者、摘要截断、标签、收藏态、时间。
- 筛选：收藏、标签、空间；搜索框进入搜索页（或内联搜索）。
- 下拉刷新；滚动追加；空状态与错误状态；离线时顶部状态条显示待同步数量。
- Android：LazyColumn + 平板双栏（列表 / 阅读区）。
- iOS：`List` + `.searchable`、`NavigationStack`，iPad 用 split view。

### 6.4 阅读器

- 渲染 `content.blocks`，块类型：`heading`、`text`（默认文本）、`image`、`game_card`、`quote`、`code`、`list`、`list_item`、`table`、`table_row`、`table_cell`、`details`、`divider`，`inlines` 提供富文本片段。
- 顶部：标题、来源、作者、发布时间、收藏、更多菜单（删除、分享链接）。
- 内容区：摘要（summary_markdown，支持安全 Markdown 子集）、关键点、原文正文、AI 评论（含 `ai_score` / `is_valuable`）、我的标注。
- 阅读样式：主题（comfortable / compact / focus / print）、背景/文字色、`color_mode`（custom / system / monet）、字体、字号 14–24、字重 400/500/600/700、行高 1.2–2.0、段距 0–40、内容宽度 600–900、对齐 left/justify、单篇覆盖（`PATCH /notes/{id}/display`）。
- 移动端字体映射：`system-ui` → 系统字体（SF Pro / Roboto）；`serif` → New York / Noto Serif；`sans-serif` → 系统无衬线；`online` → 内置精选（思源宋体/黑体子集），不访问 Fontsource/jsDelivr。
- 阅读宽度：`content_width` 在手机上解释为阅读栏最大测量宽度（以 pt/dp 计），不强制 600–900 px 物理像素。
- 阅读计时：`POST /notes/{id}/view {duration_seconds}`，上限 300 秒，离开页面或后台时上报。

### 6.5 标注

- 选择文字弹出工具栏（iOS：系统菜单/UIMenu；Android：Compose 浮动框，接近 TextToolbar 观感）：四色（yellow/green/blue/pink）+ 批注。
- 创建：`POST /notes/{id}/annotations`，字段 `block_index`、`start_offset`、`end_offset`、`selected_text`、`highlight_color`、`note_text`。
- 侧栏：列表、预览、跳回原文、修改颜色/文字（`PATCH /annotations/{id}`）、删除（`DELETE /annotations/{id}`）。
- 约束：每篇 ≤ 1000 条；单条选区 1–10000 UTF-16 单元；批注 ≤ 5000 字；块索引 0 起始前序编号；至少颜色或批注之一。

### 6.6 采集

- 分享进入：Android `ACTION_SEND`（text/plain，取 URL）；iOS Share Extension（URL）。
- Share Extension 只把 URL 写入 App Group 队列并立即返回；主 App 下次前台时提交 `POST /captures`（202 JobResponse），避免扩展内存与网络限制。
- 粘贴链接页：输入 URL → 提交 → 显示任务状态。
- 内容直传（长文/图片）：沿用 `POST /captures/uploads` + `PUT /captures/{job_id}/chunks/{position}` + `POST /captures/{job_id}/complete`，首版仅在平板/大屏提供，可列为 M4 增强。
- 任务列表：`GET /jobs?status=...`，状态 `uploading/queued/running/retrying/failed/success`，失败显示 `last_error`，可重试 `POST /jobs/{id}/retry`。

### 6.7 搜索

- `GET /notes/search?q&mode=auto&limit=30`，返回 `results`、`next_cursor`、`mode`、`semantic_status`、`message`、`retry_after`。
- UI：输入防抖 300ms；结果高亮（平台原生文本高亮）；语义索引未就绪时展示 `semantic_status` 提示并回退全文。
- 429 时按 `Retry-After` 禁用输入并提示。

### 6.8 空间

- `GET /collections`、`POST /collections`、`PATCH /collections/{id}`、`DELETE /collections/{id}`；颜色 8 种：blue/green/purple/orange/pink/red/teal/yellow；图标 6 种：folder/briefcase/book/heart/laptop/star。
- 添加/移除笔记：`POST/DELETE /collections/{id}/notes`（`note_ids` 1–100）。
- Android：Material 3 色彩容器卡片；iOS：List + 彩色 SF Symbol，图标映射到 SF Symbols。

### 6.9 回忆廊

- `GET /memory-gallery?count=10..15`，全屏卡片（标题、摘要片段、关键点、平台、标注数）。
- 操作：进入阅读、忽略（`POST /memory-gallery/dismiss {note_id}`）。
- 阅读计时同上；退出时上报。

### 6.10 设置

- 账号信息（`GET /auth/me`）、服务器、登出、清理缓存。
- 阅读偏好全局同步（`GET/PATCH /user/reading-preferences`）。
- 通知开关；关于（版本、开源许可 AGPL-3.0）。
- 不包含：LLM 配置、平台 Cookie、备份、模型用量、分享管理、Shortcut 配对（引导到网页）。

---

## 7. 平台观感要求

### Android

- Material 3（Compose Material3）：动态取色（Android 12+），`NavigationBar` / `NavigationRail` 按窗口尺寸切换；平板 `List-Detail` 布局。
- edge-to-edge、预测性返回手势、`PullToRefresh`、`Scaffold` 内边距处理；`LargeTopAppBar` 滚动折叠。
- 触觉反馈与 Material 动效；减少动态效果设置生效。
- 目标：在平板上看起来是"用 Material 写的第一方应用"。

### iOS

- SwiftUI：`NavigationStack`、`TabView`、`.searchable`、`.contextMenu`、`ShareLink`；iPad 用 `NavigationSplitView`。
- iOS 26+：Liquid Glass 工具栏/标签栏/浮层自动生效；iOS 18–25 用 `.ultraThinMaterial` 回退。
- 页面转场、弹簧动画、下拉刷新、滑动删除遵循系统。
- 目标：不出现任何"跨平台感"控件（无自绘按钮、无网页式滚动条、无统一圆角风格强制）。

---

## 8. 后端接口映射

| 功能 | 接口 | 方法 | 备注 |
| --- | --- | --- | --- |
| 服务器校验 | `/meta/version`、`/meta/capabilities` | GET | version 匿名；capabilities 需登录 |
| 登录/刷新/登出/我 | `/auth/login`、`/auth/refresh`、`/auth/logout`、`/auth/me` | POST/GET | refresh 每次轮换 |
| 笔记列表 | `/notes` | GET | cursor、limit、tag_id、favorite、collection_id、q |
| 笔记详情 | `/notes/{id}` | GET | 含内容、标注、偏好、覆盖 |
| 收藏 | `/notes/{id}` | PATCH | `{is_favorite}` |
| 删除 | `/notes/{id}` | DELETE | |
| 标注 | `/notes/{id}/annotations`、`/annotations/{id}` | GET/POST/PATCH/DELETE | |
| 阅读偏好 | `/user/reading-preferences` | GET/PATCH | |
| 单篇样式 | `/notes/{id}/display` | PATCH/DELETE | |
| 搜索 | `/notes/search`、`/notes/search/semantic` | GET | limit ≤ 30 |
| 空间 | `/collections`、`/collections/{id}/notes` | GET/POST/PATCH/DELETE | |
| 回忆廊 | `/memory-gallery`、`/notes/{id}/view`、`/memory-gallery/dismiss` | GET/POST | |
| 采集 | `/captures` | POST | 202 JobResponse |
| 任务 | `/jobs`、`/jobs/{id}`、`/jobs/{id}/retry` | GET/POST | |
| 大文件采集 | `/captures/uploads` 等 | POST/PUT | M4 增强 |

首版**不需要**服务端改动；阅读偏好的跨端同步已由 `/user/reading-preferences` 提供。若 M4 发现移动端需要批量接口或差量同步，另行提案，保持向后兼容。

---

## 9. 标注偏移黄金规则

实现必须在共享层提供以下函数并附黄金用例：

- `blockIndices(content): 每个块的前序索引`：包含结构性容器、图片、表格、折叠内容，0 起始，与网页 `lib/annotations.ts` 一致。
- `utf16Slice(text, start, end)` 与选择提取：按 UTF-16 code unit；不截断 emoji 代理对。
- 跨块选择不可标注；同一块内偏移基于该块自身文本（`inlines` 拼接；代码块用 `text`）。
- iOS 用 `NSRange`（UTF-16）作内部表示，天然与契约一致；Android 用 `String` 索引并校验代理对边界。
- 黄金用例：中文、emoji、组合字符、代码块、列表项、表格单元格、嵌套容器、旧笔记无 blocks（整篇 `content.text` 视为块 0）。

---

## 10. 离线与错误状态

| 状态 | UI 表现 |
| --- | --- |
| 首次加载 | 骨架屏 → 缓存/网络内容 |
| 离线且有缓存 | 正常阅读，顶部"离线，显示已缓存内容" |
| 离线无缓存 | 空状态 + "联网后自动缓存" |
| 待同步队列 | 顶部条：数量、失败原因、重试、取消失败操作 |
| 认证过期 | 静默刷新；失败则登录页（保留本地缓存，不自动清空） |
| 服务器不可达 | 可重试错误；不清缓存 |
| 429 | 按 `retry_after` 倒计时提示 |

---

## 11. 测试策略

| 层 | 工具 | 覆盖 |
| --- | --- | --- |
| 共享层单测 | kotlin.test + Ktor MockEngine | 认证刷新并发、错误映射、分页、重放顺序、黄金偏移用例 |
| 数据库测试 | SQLDelight 内存驱动 | 迁移、代际隔离、级联删除 |
| Android UI | Robolectric / Compose UI test + Paparazzi 截图 | 列表、阅读器、标注、双栏断点 |
| iOS UI | XCTest + swift-snapshot-testing | 同上 |
| 端到端 | CI 内起临时 Clipo（SQLite + 固定模型）供模拟器/仪器测试 | 登录→列表→阅读→标注→离线收藏→重放 |
| 验收 | 真机手动（安卓平板、iPhone） | 计划 M0–M5 验收项 |

---

## 12. 验收标准（Definition of Done）

骨架：

- [ ] `mobile/` 构建通过，CI 三条流水线全绿
- [ ] 安卓 debug apk 可在平板安装并登录真实服务器
- [ ] iOS 未签名 ipa 可侧载并完成登录与列表浏览

可用：

- [ ] 列表、阅读器、阅读样式、标注、搜索、空间、回忆廊与网页语义一致
- [ ] 分享进入、离线队列、预取与重试路径完整
- [ ] 平板双栏、iPad 分栏、横屏、动态字体不破版
- [ ] 网页创建的内容与标注在 App 正确呈现，反之亦然

真正好用：

- [ ] 冷启动 < 2s、大列表与长文档无卡顿
- [ ] TalkBack / VoiceOver 全流程可完成
- [ ] 空/错/离线/限速状态全部有明确出口
- [ ] 动效与手势完全使用平台原生实现
- [ ] 连续一周日常使用无阻断缺陷

---

## 13. 模式 B 架构预留（不实现）

需求拆解（供评估）：

| 能力 | 网页现状 | 本地优先所需的替代 |
| --- | --- | --- |
| 网页/平台抓取 | Python 提取器（Trafilatura 等） | 端侧提取或"抓取仍连服务器"的降级模式 |
| AI 摘要/评论评分 | 服务端 LLM | 端侧模型或用户自带模型密钥 |
| 全文/语义搜索 | tsvector / FTS5 / pgvector | 本地 FTS + 本地 embedding 或远程查询 |
| 同步 | 单一服务器 | WebDAV / iCloud / 自建同步协议 + 冲突策略 |

架构预留：`note`/`note_detail` 预留 `server_revision`、`deleted_at` 字段；`operation` 以幂等键为同步单位；`generation` 隔离账号；未来只替换传输层与冲突合并策略。

---

## 14. 构建与验证命令（规划）

```bash
# 共享层
cd mobile && ./gradlew :shared:jvmTest

# Android
./gradlew :androidApp:assembleDebug
adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk

# Android 模拟器（WSL2，KVM 已可用）
# 首次：安装 command-line tools → sdkmanager "platform-tools" "emulator" "system-images;android-35;google_apis;x86_64"
emulator -avd clipo -no-window -gpu swiftshader_indirect

# iOS（仅 macOS / CI）
xcodebuild -project iosApp/Clipo.xcodeproj -scheme Clipo -sdk iphoneos -configuration Release \
  CODE_SIGNING_ALLOWED=NO build
```

侧载：AltStore 或 Sideloadly；免费签名 7 天重签、最多 3 个 App、无 APNs。
