# Clipo 协作指南

## 沟通与工作方式

- 默认使用中文沟通，新增说明文档和面向用户的提示优先使用中文；代码标识符沿用现有英文命名。
- 修改前阅读相关代码与测试，保持改动聚焦，保留用户已有的修改和未跟踪文件。
- 完成后说明改动内容、验证结果及未完成的验证；不要把历史验证记录当作本次运行结果。

## 项目现状与参考资料

Clipo 是自托管的网页采集与 AI 笔记应用。目前已实现 Phase 1 基础设施和 Phase 2 核心链路：认证、模型设置、公开网页采集、后台摘要、笔记管理、失败重试和 PWA 分享入口。

- 当前能力与验收限制见 `docs/progress.md`；使用方式见 `README.md`。
- 开发与贡献约定见 `DEVELOPMENT.md`、`CONTRIBUTING.md`；设计与后续计划见 `ARCHITECTURE.md`、`IMPLEMENTATION_PLAN.md`。
- 文档中的目标目录、架构和计划不代表均已实现；实际行为以代码、迁移和可复现验证为准。
- Phase 3 已接入小红书 HTML 帖子与内嵌评论提取，尚未完成线上验收；评论分页、评分、其他平台适配器、搜索、离线阅读、浏览器扩展、Shortcut 和备份仍属后续范围。`extension/` 当前只有说明文档。

## 代码位置与运行架构

- `backend/app/main.py`：FastAPI 应用工厂 `create_app`、统一错误处理和静态文件挂载；ASGI 入口为 `app.asgi:app`。
- `backend/app/api/v1/`、`schemas/`、`services/`：API 路由、Pydantic 契约与业务服务。
- `backend/app/repositories.py`、`capture_repository.py`：带用户隔离的数据访问；`models/`、`db/`：SQLAlchemy 模型、会话和 Alembic 迁移。
- `backend/app/extractors/`、`llm/`、`tasks/`、`security/`：内容提取、模型调用、Huey 队列及安全能力。
- `backend/tests/`：pytest 单元与集成测试、离线 HTML 夹具及浏览器验收辅助服务。
- `frontend/app/`、`components/`、`lib/`、`public/`：Next.js App Router 页面、组件、API 客户端与测试、PWA 静态资源。
- `scripts/`：环境初始化、开发进程管理和浏览器冒烟验收；`deploy/`、`Dockerfile`、`docker-compose.yml`：部署入口。

后端要求 Python 3.11+；前端使用 Node.js 20+、npm、Next.js 14、React 18 和 TypeScript 严格模式。本地默认使用 SQLite，Docker Compose 使用 PostgreSQL 16；Huey 队列始终使用独立的 SQLite 文件，不依赖 Redis。

## 常用命令

除特别说明外，命令均在仓库根目录执行：

| 命令 | 用途 |
| --- | --- |
| `make install` | 使用 uv 安装后端及开发依赖，并执行前端 `npm ci` |
| `make configure` | 生成 `.env` 和随机密钥，保留已有配置 |
| `make dev` | 执行迁移，启动 API（8000）、前端（3000）和 worker |
| `make build` | 静态构建前端并复制到 `backend/app/static/` |
| `make serve` | 执行迁移，启动 API 与 worker，8000 端口托管已构建前端 |
| `make lint` | Ruff、Black 检查、ESLint 和 TypeScript 类型检查 |
| `make fmt` | Black、Ruff 自动修复和 Prettier 格式化 |
| `make test` | 后端 pytest 与前端 Vitest |
| `make migrate m="描述"` | 自动生成数据库迁移，生成后须审查 |
| `make upgrade` | 将所配置数据库迁移到最新版本 |
| `make gen-api` | 导出 OpenAPI 并生成前端 API 类型 |
| `make up` / `make down` | 启动或停止 Docker Compose 服务 |

修改 worker 代码后需重启 `make dev`。单独启动 uvicorn 时，还需运行 `.venv/bin/python -m app.tasks.worker`；API 与 worker 必须共用数据库、主密钥和 `CLIPO_QUEUE_PATH`。

## 实现约定

- Python 使用 Black 与 Ruff，行宽 100，目标 Python 3.11；新增和修改的函数补齐类型注解，公共函数明确返回类型。
- 路由负责参数校验与调用业务层。API 业务异常使用 `ClipoError`，由统一处理器生成 `error.code/message/detail`。
- 用户数据访问经仓储层显式限定 `user_id`，覆盖查询、修改、删除、缓存和任务处理，不能只依赖前端传参隔离账号。
- 前端复用 `frontend/lib/api.ts` 的请求、续期和错误处理逻辑。Access Token 仅保存在内存，刷新令牌使用 HttpOnly Cookie，保留并发续期协调机制。
- API 契约变化后运行 `make gen-api`，将 `frontend/openapi.json` 和 `frontend/lib/api-types.ts` 一并纳入改动；不要手工修改生成类型。生成过程无需启动 API，也不读取真实部署密钥。
- 保持前端可静态导出，避免依赖生产 Node.js 服务。笔记详情使用 `/notes/?id=42`，后端接口使用 `/api/v1/notes/42`。
- 数据模型变化通过 `backend/app/db/migrations/versions/` 新增 Alembic 迁移，兼容 SQLite 与 PostgreSQL，检查升级和回滚；数据搬迁脚本应具备幂等性。
- 新提取器实现 `matches`、`extract` 并返回 `CapturedContent`，在注册表中放在通用提取器之前；缺失字段留空，不猜测内容。
- 抓取与模型调用在后台任务中执行。维护任务提交后入队、分发恢复、执行租约、幂等和重试语义；模型不可用时仍保存原文，并明确显示未生成摘要。
- 变更依赖时同步对应锁文件。后端运行时锁文件更新命令为 `uv pip compile backend/pyproject.toml --python-version 3.11 --generate-hashes -o backend/requirements.lock`。

## 测试与验证

- 代码改动完成后运行 `make lint`、`make test`；涉及页面、静态资源或构建配置时再运行 `make build`。纯文档改动核对事实、路径与命令即可。
- 后端定向测试：`.venv/bin/pytest backend/tests/unit/test_extraction.py`；前端定向测试：`npm --prefix frontend test -- lib/api.test.ts`。
- 提取器必须附带 `backend/tests/fixtures/` 下的离线 HTML 夹具及测试，不能请求真实站点。LLM 测试使用固定响应或假客户端；真实接口验证须有明确任务依据。
- 复用 `backend/tests/conftest.py` 中临时数据库、临时队列和 `_env_file=None` 的测试配置，避免读取真实密钥或修改日常使用的数据。
- 浏览器验收：先 `make build`，再运行 `uv run --no-project --with playwright python scripts/smoke_capture.py`。需先安装对应 Chromium，或用 `CLIPO_TEST_CHROMIUM` 指定浏览器；截图输出到 `frontend/test-results/`。
- SQLite 测试或 PostgreSQL 迁移 DDL 生成不能替代 PostgreSQL 实机验收；浏览器分享链路验证不能替代 Android 系统分享面板验收。

## 数据与安全约束

- 不提交 `.env`、密钥、Cookie、Token、`data/`、数据库或测试截图；也不提交 `.venv/`、`node_modules/`、`.next/`、`out/`、`backend/app/static/` 等依赖和构建产物。
- 日志与错误响应不暴露凭据、笔记正文、模型返回体或包含敏感值的校验输入；敏感配置沿用现有加密存储机制。
- 修改抓取逻辑时保留 SSRF 防护：限定 HTTP(S) 与 80/443 端口、拒绝内网及 URL 凭据、校验全部 DNS 结果和每次重定向、连接固定到已验证 IP，并保留响应类型、体积和超时限制。

## 提交与文档

- 每完成一个节点（可独立验证的功能、修复或文档任务），完成相应检查后立即创建一次 Git commit，再进入下一节点；不要将多个已完成节点积攒到最后统一提交。
- 节点提交已获用户授权，无需逐次确认。仅提交该节点相关改动，保留无关的已有修改和未跟踪文件；无文件改动时不创建空提交。
- 汇报节点完成情况时附上 commit 哈希与提交说明；验证或提交失败时先处理问题，不将该节点报告为已完成。
- 提交信息遵循 Conventional Commits，例如 `feat(extractor): add bilibili adapter`；分支沿用 `feat/*`、`fix/*`。
- 行为或配置变化同步相关文档；功能进度变化同步 `docs/progress.md`，清楚区分已实现、已验证和待验收内容。
- PR 描述写清问题、结果和验证方式。
