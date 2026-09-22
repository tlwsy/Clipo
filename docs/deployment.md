# 部署指南

当前版本提供账号、模型配置、平台网页采集、Huey worker、AI 摘要、标签检索、PWA 离线、浏览器扩展、Shortcut 与笔记库备份恢复。当前源码部署不依赖预先发布的镜像。

## Docker Compose

在仓库根目录执行：

```bash
python3 scripts/init_env.py        # 生成 .env 与随机密钥，不覆盖已有文件
# 按实际部署地址修改 .env 中的 CLIPO_BASE_URL
docker compose up --build -d
docker compose logs -f app
```

访问 `http://localhost:8000` 进入设置向导，创建管理员并可选填写模型配置。注册默认关闭。

仓库的 `docker-compose.yml` 已提供两个服务：

- `app`：多阶段构建，Node.js 仅用于生成静态页面；运行时由非 root 用户启动 FastAPI 和独立 Huey worker，托管前端、API 并处理采集。进程监督器在任一子进程退出时终止容器，交由重启策略恢复。
- `db`：PostgreSQL 16，数据库端口不映射至宿主机，使用 `pg_isready` 健康检查。

应用等待数据库健康后启动，先执行 `alembic upgrade head`，迁移失败会退出。应用健康检查访问 `/api/v1/health` 并检查数据库连接。

Compose 用 PostgreSQL 连接覆盖 `.env` 中的 `CLIPO_DATABASE_URL`。本地源码开发默认 SQLite。手动设置的 `POSTGRES_PASSWORD` 若包含 `@`、`:`、`/` 等 URL 保留字符，需先处理数据库连接串的 URL 编码；配置脚本生成的十六进制密码不受此限制。

数据使用 Docker 命名卷 `pgdata` 和 `appdata` 持久化。`docker compose down` 保留数据，带 `--volumes` 则会删除卷；保存好 `.env` 中的 `CLIPO_SECRET_KEY`，恢复数据库时需要相同密钥解密已保存的 API Key。

当前开发机已通过 Docker Desktop/Compose 的镜像构建、启动、空 PostgreSQL 迁移、健康检查和静态首页检查，PostgreSQL 16 专项测试已通过；Phase 6 另在独立空 Compose 中验证设置向导、创建账号、内容直传到 worker 落库、摘要降级、中文检索和备份下载；未在该容器中请求真实平台或模型。最新范围见 [构建进度](progress.md)。

## 不使用 Docker

需要 Python 3.11+、uv、Node.js 20+、npm：

```bash
make install
make configure
make build
make serve
```

访问 `http://localhost:8000`。`make serve` 仅监听本机；用于独立服务器时可通过进程管理器运行 `CLIPO_BIND_HOST=0.0.0.0 .venv/bin/python -m app.serve`，并先执行 `make upgrade`。根目录的 `.env` 会自动加载，SQLite 相对路径以进程工作目录为准，建议始终从仓库根目录启动。

## HTTPS 与反向代理

对外访问应配置 HTTPS，并将 `CLIPO_BASE_URL` 改为实际的 `https://` 地址；此时浏览器刷新令牌会使用 Secure Cookie。PWA Service Worker 和离线缓存依赖 HTTPS（localhost 除外）；普通 HTTP 页面可添加主屏幕图标，但这不代表 Service Worker 已启用。离线能力与限制见 [离线阅读与同步](offline.md)。

可将容器映射的 8000 端口接入现有 Caddy / Nginx，示例：

```nginx
location / {
    client_max_body_size 100m;
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

如果 Nginx 本身也运行在同一 Docker 网络中，使用 `http://app:8000` 作为 upstream。当前仓库未提供代理容器或证书，需要接入已有反向代理。

## 备份与升级

设置页已提供 JSON/Markdown 导出、JSON 恢复和自动备份，见[备份与恢复](backup.md)。完整实例（含账号和配置）还需数据库备份：

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > clipo.sql
```

备份 `.env`，尤其是加密主密钥。源码更新后重新构建：

```bash
docker compose up --build -d
docker compose logs -f app
```

升级前请先备份。笔记、原始 HTML 和任务状态在应用数据库中；Huey 队列位于 `appdata` 的 `/app/data/huey.db`，应同时持久化。队列文件丢失时，worker 会按数据库中的任务状态恢复等待任务；运行中任务的租约过期后恢复。

## 排障

| 现象 | 检查方向 |
|------|----------|
| 提示缺少或无效的 `CLIPO_SECRET_KEY` | 在 `.env` 中填入 `openssl rand -hex 32` 的输出，保留此值 |
| 数据库不可用或缺表 | 检查数据库健康状态；源码运行时执行 `make upgrade` |
| 首次设置反复出现 | 检查工作目录和数据库路径，确认数据卷未删除 |
| 页面 404，但 API 可访问 | 执行 `make build`，重启 API，确认静态文件已生成 |
| 登录后立即返回登录页 | 检查访问协议与 `CLIPO_BASE_URL`，HTTPS 配置下 Cookie 不会通过普通 HTTP 发送 |
| 任务一直等待处理 | 确认 Huey worker 正在运行，并且与 API 共用数据库、主密钥和队列文件；仅启动 uvicorn 不会执行任务 |
| 抓取失败或未提取到正文 | 确认是无需登录的 HTTP(S) 文章页；当前不执行网页 JavaScript，也不支持内网和非标准端口 |
| 改了模型配置但未生效 | 检查 `.env` 中的 `CLIPO_LLM_*` 环境覆盖项 |
| WSL 提示找不到 Docker | 在 Docker Desktop 中启用对应 WSL 发行版集成，或先使用本地 SQLite 开发方式 |

## 队列与恢复

Huey 使用 SQLite SQL 存储，不依赖 Redis；即使应用数据库为 PostgreSQL，队列仍保存于 `CLIPO_QUEUE_PATH`。这是单机部署方案，暂不支持将多台机器的本地队列直接混用。默认 worker 为两个线程。

提交先事务性保存 `capture_jobs`，再分发至 Huey。worker 启动时和每分钟扫描未分发或到期任务；处理中任务持有 10 分钟租约，异常退出后会恢复。持久化状态与执行标识保证重复投递不会重复落库。暂时性失败自动重试 3 次（30 / 120 / 480 秒）；无效链接、内网地址、非 HTML、超大网页或访问受限直接失败，页面提供手动重试。

提取缓存按账号和规范化 URL 隔离，默认 24 小时。HTML 快照保存在笔记内容中，但不会返回详情页面或直接渲染；当前没有重新提取接口。
