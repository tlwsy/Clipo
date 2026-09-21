# Clipo 开发指南

## 仓库结构（目标）

当前已落地 Phase 1–2 的认证、设置、通用网页采集、Huey 队列、LLM 处理、笔记 API 与 Web 页面；Phase 3 已提供平台 Cookie 配置、小红书 HTML 帖子与内嵌评论适配器、可配置评论采集上限、评论初筛与 AI 评分，其他平台、存储和扩展随后续节点创建。应用工厂为 `app.main:create_app`，运行入口为 `app.asgi:app`。

```
clipo/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI 入口，挂载路由与静态前端
│   │   ├── config.py            配置加载：环境变量 > 数据库 > 默认值
│   │   ├── db/                  会话、基类、Alembic 迁移
│   │   ├── models/              SQLAlchemy 模型
│   │   ├── schemas/             Pydantic 请求/响应模型
│   │   ├── api/v1/              路由：auth notes captures jobs tags settings share meta
│   │   ├── services/            业务逻辑：notes tags backup media search
│   │   ├── extractors/          base.py registry.py generic.py xhs.py xiaoheihe.py video.py
│   │   ├── llm/                 client.py prompts.py orchestrator.py
│   │   ├── tasks/               Huey 任务：capture retry export backup
│   │   ├── storage/             local.py s3.py webdav.py
│   │   └── security/            密码、JWT、API Token、字段加密、SSRF 防护
│   └── tests/
│       ├── fixtures/            离线 HTML 夹具
│       ├── unit/
│       └── integration/
├── frontend/
│   ├── app/                     Next.js App Router 页面
│   ├── components/
│   ├── lib/                     API 客户端、离线队列、IndexedDB
│   ├── public/                  manifest.webmanifest、图标
│   └── sw.ts                    Service Worker
├── extension/
│   ├── manifest.json
│   ├── background/
│   ├── content/                 平台适配器
│   ├── popup/
│   └── options/
├── shortcuts/                   iOS Shortcut 文件与说明
├── docs/
├── docker-compose.yml
├── Dockerfile
└── Makefile
```

## 本地开发

推荐在仓库根目录运行（Python 3.11+、uv、Node.js 20+、npm）：

```bash
make install                       # 安装 Python 与前端依赖
make configure                     # 生成随机密钥；已有 .env 不会覆盖
make dev                           # 自动迁移，启动 API、前端与 worker
```

打开 `http://localhost:3000` 完成首次设置。API 在 8000，交互文档 `/docs`；Next 开发服务器会代理 API 与文档请求。使用 Ctrl+C 会停止 API、前端和 Huey worker 三个进程。修改 worker 相关代码后需重启 `make dev`。默认 SQLite 保存在仓库的 `data/clipo.db`，不要提交 `.env`、数据库或令牌。

### 分别启动后端和前端

```bash
# 仓库根目录，终端一
make upgrade
.venv/bin/uvicorn app.asgi:app --reload --port 8000

# 仓库根目录，终端二
.venv/bin/python -m app.tasks.worker

# 仓库根目录，终端三
npm --prefix frontend run dev
```

不使用 uv 时，可手动安装。由于 pip 的哈希校验模式不支持可编辑安装，后端依赖分两步安装：

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
.venv/bin/pip install -e './backend[dev]'
npm --prefix frontend ci
make configure
```

`backend/requirements.lock` 锁定运行时依赖，`frontend/package-lock.json` 锁定前端依赖。更新后端锁文件用 `uv pip compile backend/pyproject.toml --python-version 3.11 --generate-hashes -o backend/requirements.lock`。

### 生产静态构建

Next.js 导出的页面会自动复制到 `backend/app/static`，由 FastAPI 托管，生产环境无需 Node.js 进程：

```bash
make build
make serve                         # http://localhost:8000
```

`make serve` 会启动 API 与 Huey worker；浏览器扩展在 Phase 5 接入，当前无需构建扩展。

## 常用命令

```bash
make dev          # 启动后端与前端，自动执行迁移
make lint         # ruff + black --check + eslint
make fmt          # black + ruff --fix + prettier
make test         # pytest + vitest
make migrate m="add notes table"   # 生成迁移
make upgrade                       # 应用所有迁移
make gen-api                       # 导出 OpenAPI 与生成 TypeScript 类型
make up / make down                # docker compose
.venv/bin/pre-commit install        # 安装提交前检查
```

## 代码约定

**Python**：ruff + black，行宽 100。全量类型注解，公共函数必须有返回类型。业务异常继承 `ClipoError`，由统一异常处理器转成标准错误体。禁止在路由函数里写业务逻辑，路由只做参数校验与服务调用。

**数据访问**：所有涉及用户数据的查询经仓储层，由仓储层统一注入 `user_id` 过滤，防止越权。禁止在 service 层裸写跨用户查询。

**TypeScript**：严格模式，API 类型由后端 OpenAPI 生成（`make gen-api`），不手写接口类型。生成过程不依赖运行中的 API 或真实密钥；提交 `frontend/openapi.json` 与 `frontend/lib/api-types.ts`。浏览器仅在内存持有 Access Token，刷新令牌使用 `HttpOnly; SameSite=Strict` Cookie；API 客户端会合并并发的续期请求。

**提交信息**：Conventional Commits，例如 `feat(extractor): add xiaohongshu adapter`。

**分支**：`main` 保持可发布；功能走 `feat/*`，修复走 `fix/*`，经 PR 合入。

## 测试策略

| 层次 | 范围 | 工具 |
|------|------|------|
| 单元 | 适配器解析、评论初筛、LLM 输出解析、加密 | pytest |
| 集成 | 提交 URL 到笔记可见的完整链路 | pytest + 测试库 |
| 契约 | OpenAPI 快照，防止意外破坏客户端 | schemathesis |
| 前端 | 组件与离线队列逻辑 | vitest |
| 端到端 | 登录、保存、搜索主流程 | Playwright（Phase 4 起） |

适配器测试必须使用 `tests/fixtures/` 下的离线 HTML，不允许请求真实站点；线上结构变更时更新夹具并同步改适配器。

LLM 在测试中默认走假客户端，返回固定结构；只有显式设置 `CLIPO_TEST_REAL_LLM=1` 时才打真实接口。

## 数据库迁移

```bash
make migrate m="描述"      # 生成
.venv/bin/alembic -c backend/alembic.ini upgrade head   # 应用
.venv/bin/alembic -c backend/alembic.ini downgrade -1   # 回滚一步
```

规则：迁移必须可重复执行且可回滚；涉及数据搬迁的迁移要写成幂等脚本；生产升级前先备份（见部署文档）。

## 新增一个平台适配器

1. 在 `backend/app/extractors/` 新建文件，实现 `matches` 与 `extract`，返回 `CapturedContent`。
2. 在 `registry.py` 注册，注意匹配顺序：专用适配器先于通用适配器。
3. 放入离线夹具并写单元测试，覆盖正文、作者、时间、图片、评论字段。
4. 小红书、小黑盒的 Cookie 配置与获取教程已提供（`platform_cookies.xiaohongshu` / `xiaoheihe`）；小红书适配器通过每次任务独立的 `cookie_loader` 读取当前账号凭据。新增适配器复用 `load_platform_cookie` 与 `ScopedCookie`，由当前账号的仓储读取、解密，限定凭据发送的目标域名和 HTTPS，跨域重定向不得泄露 Cookie；有效性探测需基于可验证的登录状态。小黑盒尚未接入抓取，新增其他平台时同步补充配置与教程。
5. 如需绕过反爬，在 `extension/content/` 补一个同名适配器，输出与后端一致的 payload 结构。

## 调试建议

- 抓取问题：通用网页使用 HTTP 抓取与 trafilatura/readability；小红书适配器解析 HTML 内的 `window.__INITIAL_STATE__`，仅接受目标帖子 ID 对应的数据，按当前账号的 `capture.max_comments` 保存 0–100 条内嵌顶层评论，缺少评论时通过 `xhs_api.py` 调用签名分页接口，不执行页面脚本。适配器测试使用离线夹具，其来源与限制见 `backend/tests/fixtures/README.md`。
- 采集上限存于 `user_settings.capture_config`，使用前执行迁移 `0004_capture_settings`；默认 100，0 关闭。任务执行时读取，`CapturedContent.comment_capture_limit` 记录当次上限。降低上限只裁剪缓存的返回副本；提高到超出缓存原采集上限时重新抓取，不能将较小结果视为完整缓存。分页接入前的旧缓存会失效；当前版本缓存缺少上限字段时按 100 条上限处理，旧笔记字段为空。HTML 快照仍完整保留；不应使用 AI 候选上限代替采集上限。
- LLM 问题：先检查模型地址、密钥和额度，再用假客户端重现结构解析问题。运行日志不打印 API Key、模型返回体或笔记正文。
- 评论评分：`services/comments.py` 只选择候选，不修改原始评论；模型输入与输出使用原始位置作为 `index`，禁止用排序后的下标落库。提取缓存保留未评分内容，每次新采集读取当前账号的上限和阈值重新评分；旧笔记不会随设置变化重算。评分异常通过 `comment_score_error` 单独展示，有效摘要仍保留。
- 队列问题：直接查 `capture_jobs` 表的 `status`、`attempts`、`last_error`。
- 前端离线问题：Chrome DevTools → Application → Service Workers，配合 Network 的 Offline 模式。

## Phase 2 验收

`make dev` 和 `make serve` 都会启动 Huey worker。仅运行 uvicorn 时需要另起 `.venv/bin/python -m app.tasks.worker`；两个进程必须共用数据库、主密钥与 `CLIPO_QUEUE_PATH`。

```bash
make lint
make test
make build
# 可选浏览器验收：使用临时数据库和离线网页/模型夹具，不修改正式数据
uv run --no-project --with playwright playwright install chromium
uv run --no-project --with playwright python scripts/smoke_capture.py
```

浏览器截图写入忽略目录 `frontend/test-results/`。笔记详情使用 `/notes/?id=42`，以兼容 Next.js 静态导出；API 使用 `/api/v1/notes/42`。

### Android 模拟器连接

Windows + WSL 下已验证 MuMu 自带 ADB 可通过 `127.0.0.1:16384` 连接 Android 15 实例。路径、可复用命令、端口来源及验收边界见 [Android 模拟器连接与验收](docs/android-testing.md)。当前仅连接验证通过，PWA 安装与系统分享仍待实际验收。

## PostgreSQL 集成验证

测试支持 `.venv/bin/pytest backend/tests/integration/test_note_search.py backend/tests/integration/test_note_organization.py backend/tests/integration/test_migrations.py --postgres-url postgresql+psycopg://USER:PASSWORD@HOST/TEST_DB`。仅传入独立测试数据库；每项测试创建随机 schema 并清理，配置使用 `_env_file=None`，不读取部署密钥。默认仍用临时 SQLite。

搜索迁移拥有 SQLite FTS5 虚表/触发器和 PostgreSQL 表达式索引，Alembic 自动比较会跳过这些派生对象；增删搜索字段时需要显式迁移。先装 `pg_bigm` 再运行 `0007_note_search` 才会建立可选双字索引；无扩展使用 tsvector + 字面匹配，`/meta/capabilities` 报告启动探测结果。
