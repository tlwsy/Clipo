# Clipo 本地开发指南

本文档面向希望参与 Clipo 开发或进行本地二次开发的开发者，详细介绍工程目录结构、本地环境搭建、常用命令、代码规范、测试策略与调试技巧。

---

## 目录

- [工程目录结构](#工程目录结构)
- [环境依赖要求](#环境依赖要求)
- [本地开发快速开始](#本地开发快速开始)
- [常用开发命令](#常用开发命令)
- [架构与代码规范](#架构与代码规范)
- [测试策略与执行](#测试策略与执行)
- [数据库迁移工作流](#数据库迁移工作流)
- [平台适配器开发指引](#平台适配器开发指引)
- [调试与排障建议](#调试与排障建议)

---

## 工程目录结构

Clipo 采用前后端分离但支持单体一体化部署的代码组织形式：

```
clipo/
├── backend/                     # 后端服务源码
│   ├── app/
│   │   ├── main.py              # FastAPI 应用工厂 (create_app) 与路由挂载
│   │   ├── asgi.py              # ASGI 入口 (app.asgi:app)
│   │   ├── serve.py             # 静态集成服务入口 (API + Worker + 静态托管)
│   │   ├── config.py            # 全局配置管理 (环境变量 > 数据库设置 > 默认值)
│   │   ├── db/                  # 数据库会话、Base 声明与 Alembic 迁移
│   │   ├── models/              # SQLAlchemy 2.0 数据模型 (用户、笔记、任务、评论等)
│   │   ├── schemas/             # Pydantic 数据契约 (请求、响应与参数模型)
│   │   ├── api/v1/              # RESTful 路由层 (auth, notes, captures, jobs, tags 等)
│   │   ├── repositories.py      # 用户隔离的数据访问层 (统一注入 user_id 过滤)
│   │   ├── services/            # 核心业务服务 (提取流水线、AI 编排、备份恢复等)
│   │   ├── extractors/          # 多平台内容提取器 (小红书、小黑盒、视频、通用网页)
│   │   ├── llm/                 # 大模型客户端接入、提示词编排与结构化输出解析
│   │   ├── tasks/               # Huey 后台任务定义 (capture, retry, backup) 与 Worker
│   │   ├── storage/             # 备份与媒体存储适配层 (本地存储、S3 兼容存储、WebDAV)
│   │   └── security/            # 安全组件 (密码哈希、JWT、AES 凭据加密、SSRF 防护)
│   └── tests/                   # 自动化测试套件
│       ├── fixtures/            # 离线脱敏 HTML 样本与固定测试夹具
│       ├── unit/                # 单元测试 (解析器、安全函数、模型打分)
│       └── integration/         # 集成测试 (API 路由、数据库迁移、端到端流水线)
├── frontend/                    # 前端项目 (Next.js 14 App Router)
│   ├── app/                     # 页面路由与布局组件
│   ├── components/              # 业务与通用 UI 组件
│   ├── lib/                     # API 客户端 (api.ts)、离线缓存 (IndexedDB) 与状态
│   ├── public/                  # PWA Manifest、静态图标与资源
│   └── sw.ts                    # Service Worker 离线缓存与同步逻辑
├── extension/                   # 浏览器扩展 (Chrome / Edge Manifest V3)
│   ├── manifest.json            # 扩展清单与权限声明
│   ├── background/              # 后台 Service Worker (消息通信、上传调度)
│   ├── content/                 # 页面内容脚本与 DOM 提取器
│   ├── popup/                   # 扩展弹出层 UI
│   └── lib/                     # 扩展通用通信、分块上传与存储工具
├── shortcuts/                   # iOS 快捷指令配置、安装链接与未签名模板
├── docs/                        # 详细设计与功能专题文档
├── scripts/                     # 辅助脚本 (环境初始化、多进程启动、离线冒烟测试)
├── docker-compose.yml           # 生产部署与容器测试编排
├── Dockerfile                   # 多阶段轻量镜像构建定义
└── Makefile                     # 项目核心自动化命令集
```

---

## 环境依赖要求

在开始本地开发前，请确保你的系统已安装以下基础工具：

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)**：极速的现代 Python 包管理工具（强烈推荐，Makefile 默认集成）
- **Node.js 20+** 与 **npm**：用于前端构建与依赖管理
- **Docker & Docker Compose**（可选）：若需测试容器化集成或 PostgreSQL 生产环境

---

## 本地开发快速开始

### 1. 安装项目依赖

在项目根目录下执行以下命令，将自动使用 `uv` 创建 Python 虚拟环境并安装锁定的开发依赖，同时执行前端 `npm ci`：

```bash
make install
```

### 2. 生成本地配置与密钥

生成本地所需的 `.env` 配置文件（包含随机生成的加密密钥与安全配置）：

```bash
make configure
```
> 若根目录已存在 `.env` 文件，该命令不会覆盖已有配置。

### 3. 一键启动开发环境

```bash
make dev
```

该命令会自动应用最新的数据库迁移，并通过 `scripts/dev.py` 同时拉起三个协同进程：
- **后端 API 进程**：基于 Uvicorn，监听 `http://localhost:8000`（支持热重载）
- **前端开发服务**：基于 Next.js Dev Server，监听 `http://localhost:3000`
- **后台 Worker 进程**：基于 Huey，负责异步网页采集、重试与 AI 摘要计算

在浏览器中打开 `http://localhost:3000`，即可进行本地开发与调试。

---

### 高级选项：分别手动启动各进程

若你需要对特定进程进行断点调试或单独查看日志，也可以在三个独立终端分别启动：

```bash
# 终端 1：应用迁移并启动后端 API
make upgrade
.venv/bin/uvicorn app.asgi:app --reload --port 8000

# 终端 2：启动 Huey 任务执行 Worker
.venv/bin/python -m app.tasks.worker

# 终端 3：启动前端 Next.js
npm --prefix frontend run dev
```

> **注意**：API 进程与 Worker 进程必须共用同一份数据库、主密钥（`CLIPO_SECRET_KEY`）以及 Huey 队列文件（默认位于 `data/queue.db`）。

---

## 常用开发命令

仓库根目录提供了功能完备的 `Makefile`，建议优先使用以下命令：

| 命令 | 说明 |
| :--- | :--- |
| `make install` | 使用 uv 安装后端依赖，使用 npm 安装前端依赖 |
| `make configure` | 初始化 `.env` 配置文件与随机加密密钥 |
| `make dev` | 自动迁移数据库并并发启动 API、前端与 Worker（开发热重载） |
| `make build` | 静态编译导出前端，并将产物输出到 `backend/app/static/` |
| `make serve` | 编译后以生产托管模式启动（单个 8000 端口同时托管前端与 API） |
| `make lint` | 运行 Ruff、Black、ESLint 及浏览器扩展检查 |
| `make fmt` | 运行 Black、Ruff 自动修复与 Prettier 代码格式化 |
| `make test` | 运行后端 pytest、前端 vitest 及扩展单元测试 |
| `make upgrade` | 将当前配置的数据库升级到最新的 Alembic 迁移版本 |
| `make migrate m="..."` | 检查模型变化并自动生成新的 Alembic 迁移脚本 |
| `make gen-api` | 导出最新 OpenAPI 描述并自动生成前端 TypeScript 类型 |
| `make up` / `make down` | 启动或停止本地 Docker Compose 测试服务 |
| `make extension-package`| 打包浏览器扩展为分发 ZIP 压缩包 |

---

## 架构与代码规范

### 1. 后端工程规范 (Python)
- 遵循 Python 3.11+ 标准，使用 Black 和 Ruff，单行代码最大宽度设定为 **100**。
- **全量类型注解**：新增或修改的函数必须显式标注参数类型与返回值类型。
- **职责清晰的架构分层**：
  - **API 路由层**（`backend/app/api/`）：专注于请求参数校验、鉴权与调用业务层，严禁堆砌长篇业务逻辑。
  - **业务服务层**（`backend/app/services/`）：实现核心业务逻辑、任务编排与协同。
  - **仓储层**（`backend/app/repositories.py`）：数据持久化交互，必须**显式限定 `user_id`**，绝对禁止越权访问其他用户数据。
- **统一异常处理**：业务错误继承 `ClipoError`，由全局异常处理器统一转换为规范的 JSON 错误响应，避免直接抛出未捕获的 500 异常。

### 2. 前端规范 (TypeScript / React)
- 遵循 React 18 与 Next.js 14 (App Router) 最佳实践，严格启用 TypeScript。
- **契约自动生成**：前端 API 请求与响应类型**严禁手写**。后端契约变更后，执行 `make gen-api` 重新生成 `frontend/lib/api-types.ts`。
- **认证与令牌管理**：Access Token 仅保存在应用内存中，Refresh Token 通过带有 `HttpOnly; SameSite=Strict` 的安全 Cookie 保存，前端客户端内置并发请求的自动无感续期与防抖机制。

### 3. 安全防护底线
- **SSRF 严格防御**：后端发起抓取请求必须使用项目提供的专用 HTTP 工具，强制校验域名解析、逐次重定向检查、拦截私有 IP 范围与受限端口。
- **机密数据保护**：用户平台 Cookie、大模型 API Key 等敏感配置入库必须使用主密钥经过 AES-GCM 强加密存储；日志与错误输出中严格禁止打印敏感凭据与正文原文。

---

## 测试策略与执行

项目采用分层测试策略，确保各项功能的稳定与高内聚：

```
                    ┌────────────────────────┐
                    │  Playwright 冒烟与端到端 │
                    └───────────┬────────────┘
                    ┌───────────┴────────────┐
                    │     集成与 API 契约     │
                    └───────────┬────────────┘
                    ┌───────────┴────────────┐
                    │   单元测试与离线 Fixtures │
                    └────────────────────────┘
```

### 1. 运行常规测试套件
```bash
make test
```
该命令会并发执行：
- 后端 pytest 单元与集成测试（`backend/tests/`）
- 前端 Vitest 组件与状态测试（`frontend/`）
- 浏览器扩展测试（`extension/tests/`）

### 2. 离线夹具原则（严禁向外部发请求）
所有平台适配器的解析测试必须基于 `backend/tests/fixtures/` 目录下的离线 HTML/JSON 文件，严禁在 CI 或本地单测中直接请求外部网站（如小红书、B站等）。

定向运行提取器测试：
```bash
.venv/bin/pytest backend/tests/unit/test_extraction.py
```

### 3. PostgreSQL 集成测试
本地默认测试使用临时 SQLite 数据库。若需验证针对 PostgreSQL 16 的全文检索、JSONB 与迁移兼容性，可传入测试数据库连接串：

```bash
.venv/bin/pytest backend/tests/integration/test_note_search.py \
  --postgres-url postgresql+psycopg://postgres:secret@localhost:5432/clipo_test
```

### 4. 浏览器端到端与离线冒烟验收
在构建前端（`make build`）后，可运行离线 Playwright 脚本验收整个流程：

```bash
uv run --no-project --with playwright python scripts/smoke_capture.py
```
> 测试过程中截取的页面快照将保存到 `frontend/test-results/`（该目录已被 git 忽略）。

---

## 数据库迁移工作流

Clipo 使用 Alembic 管理数据库 Schema 演进。数据库架构设计同时兼顾 **SQLite**（开发与轻量部署）与 **PostgreSQL**（高并发生产环境）。

### 1. 自动生成迁移脚本
修改 `backend/app/models/` 中的模型后，运行：
```bash
make migrate m="add_summary_tags"
```
Alembic 将在 `backend/app/db/migrations/versions/` 下生成新的迁移版本文件。

### 2. 审查与编写迁移规范
- 生成迁移文件后必须人工审查，确保其在 SQLite 和 PostgreSQL 上均可无误执行。
- 若迁移涉及现有数据搬迁或清洗，脚本应保证**幂等性**（即重复执行不会破坏已有数据）。
- 注意 SQLite 仅支持部分 `ALTER TABLE` 操作，复杂表结构变更需使用 `batch_alter_table`。

### 3. 应用与回滚迁移
```bash
# 应用最新迁移
make upgrade

# 回滚最近一步迁移
.venv/bin/alembic -c backend/alembic.ini downgrade -1
```

---

## 平台适配器开发指引

为新平台编写抓取提取器通常仅需 4 步：

1. **新建适配器**：在 `backend/app/extractors/` 新建文件（如 `zhihu.py`），实现 `matches(url: str) -> bool` 与 `extract(url: str, payload: dict | None) -> CapturedContent` 两个核心方法。
2. **注册适配器**：在 `backend/app/extractors/registry.py` 的注册列表中加入新提取器。**务必将其置于 `GenericExtractor`（通用提取器）之前**。
3. **编写离线夹具与测试**：保存目标平台的典型脱敏 HTML 样本至 `backend/tests/fixtures/`，并在 `backend/tests/unit/test_extraction.py` 中编写单元测试。
4. **扩展端直传适配（可选）**：若目标平台需要严格登录态或防爬限制极严，可在浏览器扩展的 `extension/content/` 目录下添加同名解析脚本，支持在用户已登录的浏览器内直接采集 DOM 结构。

---

## 调试与排障建议

- **抓取失败与排查**：检查 `capture_jobs` 数据表中对应任务的 `status`、`attempts` 与 `last_error` 字段；检查目标 URL 是否命中 SSRF 防护规则。
- **LLM 大模型调用**：检查 `.env` 或用户设置中的模型 Base URL、API Key 与模型名称是否正确。本地排错建议使用 Mock 客户端或固定的返回样本，以防消耗真实额度。
- **任务队列堆积**：检查 Worker 进程是否正常运行；若存在孤儿任务或锁竞争，Worker 启动时会自动根据租约机制重新认领漏处理的任务。
- **PWA / Service Worker 离线调试**：在 Chrome DevTools 打开 **Application -> Service Workers**，可手动切换 **Offline** 模式调试离线缓存与写操作同步。
