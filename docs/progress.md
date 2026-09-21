# 构建进度

2026-09-20：已完成 Phase 1 基础设施与 Phase 2 核心链路的代码和本地验收。

2026-09-21：进入 Phase 3，新增首个节点“平台 Cookie 配置”。设置页提供小红书、小黑盒 Cookie 的获取教程、加密保存、替换和清除，按账号隔离且不回显凭据；复用既有数据库字段，无需新迁移。保存仅代表已配置，尚未验证登录有效性，也尚未用于平台抓取。

2026-09-21：推进 Phase 3 第二节点“小红书 HTML 采集”。支持帖子链接及短链接跳转，提取 HTML 内嵌的正文、图片链接、作者、发布时间和最多 100 条顶层评论；后台任务读取当前账号 Cookie，保留 SSRF 防护，限定官方 HTTPS 主机接收凭据。新增登录失效、访问限制、频控及结构变化提示。该节点不含评论分页、价值评分或独立登录有效性探测，尚未完成真实平台验收。

## 当前可用

- FastAPI 应用工厂、配置、统一错误体、健康检查与 OpenAPI；PostgreSQL / SQLite 模型和可回滚的 Alembic 迁移。
- 初始化向导、账号与注册开关、Argon2id 密码、JWT 与刷新令牌轮换、HttpOnly Cookie、自动续期、API Token 管理；配置按账号隔离，模型密钥加密存储。
- 小红书、小黑盒 Cookie 设置：加密保存、独立替换与清除，设置页附获取教程；读接口只返回保存状态。小红书后台采集使用当前账号凭据；小黑盒抓取与独立有效性探测仍待接入。
- 小红书适配器优先于通用适配器，支持 `/explore/帖子ID`、`/discovery/item/帖子ID` 和 `xhslink.com` 短链接；只读取目标帖子的内嵌状态，不回退保存登录页或推荐帖。已有评论含作者、内容、点赞及回复数，通过现有笔记 API 和详情页展示；评论缺失或不完整时页面有提示。
- 公开网页采集：统一 `CapturedContent`、可扩展的 Extractor 注册表、trafilatura 正文提取与 readability 兜底；标题、作者、发布时间、图片来源链接和原始 HTML 快照。
- 抓取安全：HTTP(S) / 80、443 端口限制；检查全部 DNS 结果和每次重定向，连接固定到验证后的 IP 并保留 TLS SNI；不使用环境代理；响应类型、体积及时间上限。抓取器不执行页面脚本。
- 持久化 Huey SQLite 队列与独立 worker；任务状态机、30 / 120 / 480 秒重试、失败后手动重试；任务表分发恢复、10 分钟运行租约、执行标识防止重复落库。API 先提交任务再入队，漏投递由 worker 恢复。
- OpenAI 兼容 HTTP 客户端、提示词、Pydantic JSON 结构校验、正文预算截断和一次兼容重试。没有密钥或模型调用失败时，仍保存完整原文，并明确显示“未生成摘要”。
- 笔记、来源和评论落库；按账号与 URL 隔离的 24 小时提取缓存；幂等提交；游标分页；笔记删除级联清理来源与评论，保留任务历史。
- `POST /captures`、`GET /jobs`、`GET /jobs/{id}`、`POST /jobs/{id}/retry`、`GET /notes`、`GET /notes/{id}`、`DELETE /notes/{id}`；同步生成 OpenAPI 与 TypeScript 类型。
- Web 笔记列表、链接保存、实时队列、详情、Markdown 摘要、要点、建议标签、原文、图片链接与删除确认；模型设置新增正文预算。
- PWA Manifest、192 / 512 图标、Service Worker 注册和 GET 分享入口。未登录时暂存分享内容，登录后自动继续，以幂等键防止重复提交。当前阅读需要联网。
- `make dev` 启动 API、前端和 worker；`make serve` 与 Docker 入口监督 API / worker 两个进程；队列路径在容器数据卷中持久化。

## Phase 1–2 验证记录（2026-09-20）

- 后端 **69 项**测试通过，涵盖原有认证、设置与安全测试，以及完整 URL → Huey → 提取 → 摘要/降级 → 笔记链路、离线 HTML 元数据/兜底、SSRF 与响应限制、幂等并发、缓存过期、用户隔离、重试耗尽、持久化重试、队列恢复、过期租约、旧 worker 防重、删除级联和迁移一致性。
- 前端 **10 项**测试通过：原有会话续期等 7 项，加上分享 URL 提取与无效分享输入 3 项。
- `make lint`、`make test`、`make build` 通过；PostgreSQL 迁移 DDL 生成通过，额外验证了 Phase 1 已有账号在 Phase 2 升级及回退后仍保留。DDL 生成不替代 PostgreSQL 实机验收。
- Chromium 使用临时数据库、独立 API/worker 进程及离线网页/模型夹具，完成首次设置、原文保存、模型配置、摘要和要点、删除、失败后手动重试、退出登录后分享并登录继续保存；Manifest 图标与 Service Worker 可访问，未发现脚本错误。已检查 1440px 桌面和 390px 手机布局。
- 浏览器验收可复现：构建后运行 `uv run --no-project --with playwright python scripts/smoke_capture.py`；需要已安装对应 Chromium，可通过 `CLIPO_TEST_CHROMIUM` 指定现有浏览器路径。截图在忽略目录 `frontend/test-results/`。
- 测试不请求真实网页或真实 LLM，不修改正式数据库中的账号与笔记。

## Phase 3 首节点验证（2026-09-21）

- 本次运行 `make lint`、`make test`、`make build` 全部通过；后端 **86 项**、前端 **10 项**测试通过。新增 17 项平台设置测试覆盖凭据加密与不回显、认证与账号隔离、两平台独立更新、留空保留、替换/清除，以及非法 Cookie 不产生部分更新；测试仍有既有的 Starlette/httpx 与 AnyIO 弃用提示。
- 已运行 `make gen-api`，同步 OpenAPI 与 TypeScript 类型。复用 `user_settings.platform_cookies`，未新增模型或迁移。
- 本次 Chromium 浏览器验收通过：平台 Cookie 保存、刷新保留、替换、单独/同时清除、请求失败后保留输入并重试，以及教程展开；检查了 1440px 桌面和 390px 手机布局，无横向溢出或脚本错误。原有初始化、采集、摘要、删除、重试及分享登录链路也通过。
- 默认 Playwright 依赖的 Chromium 版本尚未安装，本次通过 `CLIPO_TEST_CHROMIUM=/home/tlwsy/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome uv run --no-project --with playwright python scripts/smoke_capture.py` 使用已有浏览器完成验收；他机请替换为实际路径或安装对应 Chromium。
- 全部验证使用临时数据库、离线网页/模型夹具和虚构 Cookie，未访问真实平台、验证真实 Cookie 或真实模型；未重跑 Docker、PostgreSQL 与 Android 真机验收。

## Phase 3 小红书 HTML 采集节点验证（2026-09-21）

- 本节点运行 `make lint`、`make test`、`make build` 全部通过：后端 **135 项**、前端 **10 项**测试通过。新增 49 项后端测试覆盖帖子及缺失字段解析、内嵌评论去重与上限、短链接、严格域名匹配、Cookie 的 HTTPS/主机/端口限制、重定向与响应 Cookie 防泄露、私网 DNS 拒绝、失败分类、并发账号隔离、缓存隔离及更新 Cookie 后重试。仍有既有的 Starlette/httpx 与 AnyIO 弃用提示。
- Chromium 使用临时 SQLite、独立 API/worker、虚构 Cookie 与离线 HTML/模型，验证小红书登录失败、更新 Cookie、手动重试、帖子元数据/原文/图片及 10 条评论展示；同时回归原有初始化、通用采集、摘要、设置、删除、分享与登录流程。1440px 桌面与 390px 手机布局无横向溢出或脚本错误，截图已检查且仅保留于忽略目录 `frontend/test-results/`。
- 浏览器命令：`CLIPO_TEST_CHROMIUM=/home/tlwsy/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome uv run --no-project --with playwright python scripts/smoke_capture.py`；其他环境请替换浏览器路径。无标题与无文字帖子的原始字段保持为空，界面提供对应提示。
- 沿用现有 API 契约、数据库字段和依赖，无需新迁移或生成类型变更。没有请求真实小红书/LLM，未验证真实 Cookie、线上反爬兼容性、Docker、PostgreSQL 实机或 Android 系统分享；不将离线评论样本视为 M3 线上验收通过。

## 验收限制

- 当前 WSL 未启用 Docker Desktop 集成，容器和 PostgreSQL 实机验收仍待完成。
- Android 真机上的 PWA 安装与系统分享面板尚未验证；已验证同一分享 URL 的浏览器链路和 Manifest。
- 尚未使用真实模型密钥验证供应商兼容性；已用固定返回和 HTTP 协议夹具验证摘要、失败重试与降级。
- 通用抓取只支持公开的静态 HTML，不支持需要登录或 JavaScript 渲染的站点。图片只保留外链，不下载媒体；HTML 快照用于后续重新提取，当前没有相应 API。
- 建议标签尚未变成可管理标签；通用网页不抓评论。小红书仅解析页面已有的最多 100 条顶层评论，不请求签名接口、评论分页或楼中楼，尚未进行评论初筛和评分。
- 小红书夹具为人工构造的最小回归样本，不能证明当前线上结构或反爬兼容性；真实 Cookie、真实帖子与登录状态有效性尚未验证。HTTP 401/明确登录页才提示登录失效，403/验证码归为访问限制；公开帖子采集成功不代表 Cookie 已通过验证。

## 当前阶段与后续节点

**Phase 3：平台专项，进行中。** 已实现小红书、小黑盒的 Cookie 配置与加密，以及小红书 HTML 帖子/内嵌评论采集和失败诊断。接下来补齐可验证的 Cookie 有效性探测、评论分页与上限配置、小黑盒和视频平台适配器、评论初筛及 LLM 评分。小红书真实平台验收仍待完成，当前尚不满足 M3“关键平台可用”的验收标准。

检索、标签管理、iOS Shortcut 与离线访问在 Phase 4；扩展及内容直传在 Phase 5；导出、自动备份、CI 与发布在 Phase 6。限流、公开分享、重新摘要等额外接口仍未实现。
