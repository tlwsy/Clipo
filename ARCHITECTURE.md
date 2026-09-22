# Clipo 技术架构

本文档描述 Clipo 的系统架构、技术选型理由和核心数据模型。总体方案作为设计基线；当前已推进至 Phase 5，实际能力与验收限制以 [构建进度](docs/progress.md) 为准。

## 1. 设计目标与约束

| 目标 | 说明 |
|------|------|
| 自托管优先 | 用户完全掌握数据与 LLM 费用，无中心化服务 |
| 极简录入 | 分享即保存，默认无需用户二次确认 |
| 中国大陆可用 | 国内 LLM 优先，小红书/小黑盒为一等公民 |
| 部署轻量 | 不引入 Redis 等额外常驻服务 |
| 多端统一 | 一套 RESTful API 服务 PWA、扩展、Shortcut、未来 Flutter 端 |

非目标（MVP 不做）：协作编辑、笔记双向链接、全文向量检索、移动原生端。

## 2. 系统总览

```
                 ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   录入入口       │  PWA 分享     │  │ 浏览器扩展    │  │ iOS Shortcut │
                 │ (Share Target)│  │ (DOM 抓取)   │  │ (静默 POST)  │
                 └───────┬──────┘  └──────┬───────┘  └──────┬───────┘
                         │  JWT           │ API Token       │ API Token
                         └────────────────┼─────────────────┘
                                          ▼
                              ┌────────────────────────┐
                              │   FastAPI (REST API)    │
                              │  认证 / 笔记 / 任务 / 设置 │
                              └───────────┬────────────┘
                                          │ 入队
                                          ▼
                              ┌────────────────────────┐
                              │   Huey Worker (同进程或独立) │
                              └───────────┬────────────┘
                     ┌────────────────────┼────────────────────┐
                     ▼                    ▼                    ▼
            ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
            │ Extractor 适配层 │   │  LLM 编排层     │   │  媒体存储层     │
            │ 通用/小红书/小黑盒│   │ HTTP + JSON校验│   │ 本地 / S3      │
            └────────┬───────┘   └────────┬───────┘   └────────┬───────┘
                     └────────────────────┼────────────────────┘
                                          ▼
                              ┌────────────────────────┐
                              │  PostgreSQL (或 SQLite) │
                              │  笔记 / 评论 / 标签 / 队列 │
                              └────────────────────────┘
```

后端同时以静态文件形式托管 Next.js 导出的前端产物，因此最小部署只有两个容器：应用 + 数据库。

## 3. 技术选型与理由

### 后端：Python 3.11 + FastAPI
爬虫生态（DrissionPage、parsel）与 LLM 生态（LangChain）都在 Python 最成熟，这两者是本项目的技术核心。FastAPI 自动生成 OpenAPI 文档，对多客户端联调友好。

### 数据库：PostgreSQL 默认，SQLite 可选
PostgreSQL 承担全文检索（`tsvector`）与 JSONB 存储；SQLite 面向单用户极简部署，检索走 FTS5。通过 SQLAlchemy 抽象，检索层针对两种后端分别实现。

### 任务队列：Huey（SQLite SQL 存储）
异步抓取与 LLM 调用脱离请求生命周期。Phase 2 使用独立 worker 进程与两个线程，Huey 队列保存在持久化的 SQLite 文件中，即使业务数据使用 PostgreSQL 也不需要 Redis。任务表充当分发恢复来源，启动和每分钟恢复漏投递任务；10 分钟租约及执行标识防止旧 worker 重复落库。当前支持单机部署。

### LLM 接入：OpenAI 兼容 HTTP 客户端 + 可选 One API 网关
Phase 2 直接使用 httpx 与 Pydantic 完成提示词、JSON 结构校验和一次兼容重试，无需引入完整 LangChain 依赖。One API 仍可作为可选外置网关。模型失败只降级摘要，保留完整原文；正文预算按 UTF-8 字节保守截断。后续复杂编排可替换客户端实现。

### 抓取：HTTP 正文提取，后续补充浏览器与扩展 DOM 直取
Phase 2 通过 HTTP 抓取静态 HTML，使用 trafilatura 提取正文、readability 兜底。Phase 3 小红书适配器优先匹配官方域名与短链接，解析 HTML 内嵌状态中的目标帖子及已有评论；Cookie 按任务所属账号读取，仅发送到明确允许的官方 HTTPS 主机，短链接不接收 Cookie，站外跳转直接拒绝。DNS 解析与每次重定向均检查公开 IP，连接固定到已验证 IP 并保留 TLS SNI；限制端口、响应体大小和读取时限，清空 HTTP 客户端的响应 Cookie，避免固定 IP 导致跨主机复用。不执行网页 JavaScript。

DrissionPage 对国内站点的反爬处理更贴合，且可在无头与有头模式间切换。但小红书/小黑盒的登录态最稳妥来源是用户自己的浏览器，因此浏览器扩展的 DOM 直取是首选路径，服务端抓取是移动端场景的兜底。

### 前端：Next.js 14 静态导出 + Service Worker
静态导出让后端单进程即可托管前端，部署简单。PWA 能力（Share Target、离线缓存、安装到桌面）是 iOS 侧的唯一可行路线，也是 Android 首期形态。

## 4. 内容提取流水线

```
1. 接收       客户端 POST /api/v1/captures，携带 url，可选 payload（扩展直传的 DOM 内容）
2. 去重/缓存   按 url 规范化后哈希，命中 extraction_cache 且未过期则跳到步骤 5
3. 抓取       Extractor 适配器选择：小红书 / 小黑盒 / 视频 / 通用网页
4. 规范化      产出统一的 CapturedContent 结构（标题、正文、作者、时间、图片、评论）
5. 评论初筛    按点赞/回复数排序取 Top N（默认 30），过滤过短与纯表情
6. LLM 处理    单次调用产出：Markdown 摘要、要点列表、建议标签、每条评论的价值评分
7. 评论定稿    评分达到阈值（默认 0.6）标记 is_valuable，原始评论全部保留
8. 媒体处理    下载缩略图；按设置决定是否下载原图
9. 落库        写入 notes / sources / comments / tags，更新任务状态为 success
```

当前已实现步骤 1–7 和 9，其中小红书评论限于 HTML 内嵌数据，媒体下载尚未接入。暂时性抓取/处理失败：标记 `retrying`，重试 3 次（30s / 2min / 8min），最终置 `failed`。非法地址或不可访问内容直接失败；用户可在队列页手动重试。LLM 失败降级保存原文与全部已采集评论，任务仍为 `success`。

### Extractor 适配器契约

每个平台实现同一接口，新增平台只需新增一个适配器并注册：

```python
class Extractor(Protocol):
    name: str
    def matches(self, url: str) -> bool: ...
    def extract(self, url: str, payload: dict | None) -> CapturedContent: ...
```

`CapturedContent` 为稳定的内部结构，隔离平台变动对下游的影响。当 `payload` 存在（扩展直传）时，由 `services/captures.py` 校验和规范化，在 worker 中直接进入摘要/评分流程，不调用提取器、不发起网络请求、不读写网页提取缓存。

## 5. LLM 编排

单次调用完成摘要与评论评分，减少费用与延迟。提示词要求返回 JSON，客户端请求 JSON mode（失败时兼容普通 JSON），并用 Pydantic 校验结构与评论编号：

```json
{
  "summary_markdown": "……",
  "key_points": ["……"],
  "suggested_tags": ["……"],
  "comment_scores": [{"index": 0, "score": 0.82, "reason": "给出具体参数"}]
}
```

Phase 3 已接入独立的评论采集上限：`capture.max_comments` 默认 100，范围 0–100，0 关闭评论采集。小红书提取器按页面顺序保留有效且编号不重复的评论，`CapturedContent.comment_capture_limit` 记录当次上限；缓存只在原上限足以覆盖当前上限时复用，降低上限裁剪返回副本，提高至超出原上限则重新抓取。设置在任务执行时按账号读取，已有笔记与 HTML 快照保留。

评论初筛与评分在采集之后执行：按点赞、回复数降序排列，Unicode/空白规范化后去重，过滤少于 5 个文字或数字字符以及纯表情的评论，选取最多 N 条（默认 30）。已采集评论全部保留，候选仍使用原始位置作为编号。仅接受每个候选恰好一次的有限 0–1 分数及非空理由；重复、遗漏、越界编号或非法分数触发一次重试。若评分仍失败但摘要有效，保留摘要，通过 `comment_score_error` 单独提示。

长正文按 token 预算保守截断（默认 8000，以 UTF-8 字节数作为上界，因此中文正文通常保留更少）。评论另限每条 1000 UTF-8 字节、整个评论 JSON 数组 8000 字节，因此实际评分条数可能小于 N；模型输出预算为 `2000 + 100 × 实际候选数`。截断只影响模型输入。评分与 `is_valuable` 落库，提取缓存仅保存原始内容，旧笔记不自动重新评分。模型与 API Key 由用户在设置中配置，按用户隔离存储并加密于数据库。

## 6. 数据模型

```sql
-- 用户与认证
users(id PK, username UNIQUE, email UNIQUE, password_hash, is_admin, created_at)
refresh_tokens(id PK, user_id FK, token_hash, expires_at, revoked_at)
api_tokens(id PK, user_id FK, name, token_hash, last_used_at, created_at)

-- 来源与笔记
sources(id PK, platform, origin_url, author, author_url, published_at, metadata JSONB)
notes(id PK, user_id FK, source_id FK, title, url, content JSONB,
      summary_markdown, key_points JSONB, status, created_at, updated_at)
comments(id PK, note_id FK, author, content, likes, replies,
         ai_score, ai_reason, is_valuable, position)

-- 组织与分享
tags(id PK, user_id FK, name, color, UNIQUE(user_id, name))
notes_tags(note_id FK, tag_id FK, PRIMARY KEY(note_id, tag_id))
shared_links(id PK, note_id FK, token UNIQUE, expires_at, view_count, created_at)

-- 运行时
capture_jobs(id PK, user_id FK, url, source_hint, payload JSONB, status,
             attempts, last_error, note_id FK NULL, created_at, updated_at)
extraction_cache(id PK, user_id FK, url_hash, content JSONB, expires_at, UNIQUE(user_id, url_hash))
user_settings(user_id PK FK, llm_config JSONB, platform_cookies JSONB, capture_config JSONB,
              media_policy, backup_config JSONB)
media_assets(id PK, note_id FK, kind, original_url, storage_key, width, height, bytes)
```

该模型同时包含后续阶段规划表；当前迁移的精确结构以 `backend/app/db/migrations/` 为准。Phase 2 还为来源添加 `user_id`，为笔记添加 `suggested_tags`、`summary_error`，为任务添加幂等键、下次重试时间与执行租约。

要点：
- `notes.content` 保存规范化后的原始内容（JSONB），`summary_markdown` 保存 LLM 产出，二者分离，便于重新生成摘要而不丢原文。
- `capture_jobs` 同时充当队列可见性来源，支撑"保存队列"页面。
- `user_settings.llm_config` 与 `platform_cookies` 中的敏感字段使用应用层对称加密（密钥来自 `CLIPO_SECRET_KEY`），数据库备份泄露不直接暴露凭据。
- 多用户完全隔离：所有查询强制带 `user_id` 条件，仓储层统一注入，不依赖调用方自觉。

## 7. 认证与授权

| 客户端 | 凭据 | 生命周期 |
|--------|------|----------|
| PWA | Access JWT（15 分钟）+ Refresh Token（30 天，DB 存哈希） | 自动续期 |
| 扩展 / Shortcut | API Token（用户在设置页生成，仅展示一次） | 长期，可撤销 |
| 分享链接 | 无需登录，凭 token 只读单条笔记 | 可设过期 |

密码使用 Argon2id 哈希。API Token 存储哈希值，校验时比对。所有写接口要求认证；分享链接接口是唯一匿名可读入口，且只返回该条笔记的公开字段。

## 8. API 约定

- 前缀 `/api/v1`，JSON 输入输出，时间统一 ISO 8601 UTC。
- 错误体：`{"error": {"code": "...", "message": "...", "detail": {...}}}`。
- 列表接口游标分页：`?cursor=<opaque>&limit=50`，返回 `next_cursor`。
- 幂等：`POST /captures` 接受 `Idempotency-Key`，重复提交返回同一 job。

完整端点见 [docs/api.md](docs/api.md)。

## 9. PWA 离线策略

| 资源类型 | 策略 |
|----------|------|
| 构建产物（JS/CSS/字体） | Cache First，构建哈希命名，版本更新即失效 |
| API 读请求 | Network First，2 秒超时回退缓存 |
| 最近 50 条笔记 | 后台预缓存至 IndexedDB，离线可读 |
| 写操作 | 离线时入本地待发队列，恢复网络后重放 |

Service Worker 检测到新版本时，页面顶部提示"有新版本，点击刷新"，不强制刷新。前端启动与轮询时比对 `/api/v1/meta/version`，版本不匹配同样提示。

Android 通过 Web App Manifest 的 `share_target` 声明接收分享；iOS 无此能力，由 Shortcut 直接调用 API 补齐。

## 10. 浏览器扩展架构

```
manifest v3
├── background (service worker)   接收指令、调用后端 API、处理通知
├── content script (按需注入)      读取页面 DOM，按平台适配器提取结构化内容
├── popup                          显示保存状态、快捷标签
└── options                        配置服务器地址与 API Token
```

安装权限只申请 `activeTab`、`storage`、`contextMenus`、`scripting`，不申请 `<all_urls>`；设置页按需申请配置服务器的单个 HTTP(S) 主机权限（Chrome 授权不区分端口），Token 请求仍固定到配置的 origin 且拒绝跳转；仅在用户主动触发时通过 `activeTab` 注入。扩展侧适配器与后端 Extractor 共享字段定义，抓取结果作为 `payload` 直传，后端不再重复请求目标站点。

## 11. 媒体与备份

媒体：默认下载缩略图用于列表展示，原图按用户设置决定是否落盘；存储抽象支持本地文件系统与 S3 兼容对象存储。

备份：
- 本地导出：完整 JSON（可回导）+ Markdown 目录（人类可读）
- S3 兼容：阿里云 OSS、腾讯云 COS、MinIO
- WebDAV：坚果云、Nextcloud

导出任务同样走 Huey，产物落盘后提供下载链接，大库不阻塞请求。

## 12. 部署拓扑

```
docker-compose
├── app        FastAPI + Huey worker + 静态前端      :8000
├── db         PostgreSQL 16                        :5432 (内部)
└── proxy      Nginx（可选，HTTPS 与反向代理）        :80/:443
```

首次访问进入 Web 设置向导：创建管理员、配置 LLM、选择媒体与备份策略。向导结果写入数据库；环境变量优先级高于数据库配置，便于容器化覆盖。

## 13. 安全考量

- 所有平台 Cookie 与 API Key 加密存储，日志脱敏，不写入错误上报。
- 抓取目标 URL 做 SSRF 防护：禁止内网网段、非 HTTP(S) 协议、用户凭据和非 80/443 端口；验证全部 DNS 结果与每次重定向，连接固定到已校验 IP。
- 分享链接使用高熵随机 token，支持过期与撤销。
- 扩展与 Shortcut 的 API Token 可独立命名与撤销，便于定位泄露来源。
- 服务默认不暴露注册入口；是否开放注册由管理员在设置中决定。

## 14. 可扩展点

新增平台：实现后端 Extractor + 扩展侧适配器，注册即可，无需改动流水线。
更换模型：只要提供 OpenAI 兼容端点即可，或经 One API 网关转换。
新增客户端：Flutter 端复用现有 REST API 与 JWT 流程，无需后端改造。
