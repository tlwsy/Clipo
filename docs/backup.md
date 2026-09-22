# 备份与恢复

备份以当前账号的笔记库为单位，包括笔记原文和 HTML 快照、摘要与要点、来源、评论及评分、标签（含未关联标签）、收藏状态、创建/修改时间与图片链接。账号、登录令牌、模型密钥、平台 Cookie、运行队列及提取缓存不在导出范围。当前媒体仅保存外链，备份恢复媒体引用，不会下载图片文件。

## 导出和导入

网页设置 → **备份与恢复** 可创建导出、下载 ZIP、选择 `library.json` 并确认追加导入；下方任务列表显示后台进度与失败原因，支持重试。导入完成后刷新笔记列表即可看到恢复的笔记。

使用 API Token 或登录会话：

1. `POST /api/v1/backups/exports`，请求 `{"request_key":"自行生成的唯一值"}`。相同键复用同一导出任务。
2. `GET /api/v1/backups` 查询最近 50 个任务；`success` 后访问 `GET /api/v1/backups/{id}/download` 下载 ZIP，下载同样要求认证。
3. ZIP 内的 `library.json` 是版本 1 的完整笔记库，`markdown/` 为人类可读的笔记目录。
4. 在新实例完成账号初始化，将解压后的 `library.json` 作为请求正文发送至 `POST /api/v1/backups/imports`（`Content-Type: application/json`）。导入在后台完成，无需原实例密钥。
5. 导入追加到当前账号，重新分配数据库 ID，不覆盖已有笔记。相同文件的重复提交复用原任务，防止重试造成重复导入；修改文件会视为新的导入。

导入先完整校验，再以单事务恢复；失败不会留下部分笔记。失败任务可通过 `POST /api/v1/backups/{id}/retry` 重试。所有文件与查询按账号隔离，任何用户都无法下载其他账号的备份。

JSON 大小上限 100 MiB，导出也遵循相同限制，超出请使用数据库备份。反向代理需允许 100 MiB 上传，例如 Nginx `client_max_body_size 100m;`。ZIP 不作为导入输入，避免解压炸弹和路径写入风险。

API 与 worker 共用 `CLIPO_QUEUE_PATH`，文件存于其父目录的 `exports/` 与 `imports/`。后台任务具有一小时租约；worker 启动和每分钟恢复遗漏投递与中断任务，暂时错误最多尝试四次，失败原因不含正文或凭据。

## 实例灾难恢复

笔记库导出不替代整个实例备份。保留数据库备份、数据卷和 `.env`，尤其是 `CLIPO_SECRET_KEY`，才可恢复账号及加密配置。PostgreSQL 操作见[部署指南](deployment.md)。导出包含私有笔记与 HTML，请自行妥善保管下载文件。

## 自动备份目标

设置页选择目标并保存后，可点“立即备份”，或填写五段 Cron，例如 `0 4 * * *` 为每天 04:00。采用部署者配置的 `CLIPO_TIMEZONE`（默认 Asia/Shanghai）。计划留空只接受手动触发；关闭目标后不创建新计划任务。每分钟检查一次，以账号与 UTC 分钟去重；服务停机期间错过的计划不补跑，运行中断的已创建任务会恢复。日与星期同时指定时须同时满足（Huey 语义）。

| 目标 | 配置与保留 |
| --- | --- |
| 本地 | 写入 `CLIPO_BACKUP_PATH/<账号ID>/`，默认仓库 `data/backups/`（Docker `/app/data/backups/`）；先写临时文件再原子替换，成功后保留最近 `CLIPO_BACKUP_KEEP` 份（默认 10） |
| S3 兼容 | 填 endpoint、bucket、region、Access Key 与 Secret Key；使用 path-style 和 SigV4 PUT，bucket 须已存在。MinIO 已做实际上传/下载验证；OSS/COS 等供应商的 endpoint 与 path-style 兼容性需按其配置验证 |
| WebDAV | 填 endpoint、用户名、应用密码及目录前缀；endpoint 加前缀对应目录须已存在，支持 Basic 认证与 PUT。WsgiDAV 已做实际上传/下载验证，坚果云/Nextcloud 等账户需自行验收 |

远端对象名为 `<前缀>/<账号ID>-<任务ID>.zip`，同一任务重试覆盖同一对象；远端保留策略在存储服务配置，不由 Clipo 删除。凭据按账号加密保存且不回显；更换目标类型、地址或用户名时必须重新填写凭据。任务执行时读取已保存配置，正在上传的任务继续使用其当次读取的配置。

默认只允许公开 HTTPS/443 存储；每次解析验证全部 DNS 结果、连接固定到已验证地址、拒绝重定向，不使用系统代理。自建内网 MinIO 可由管理员在 `.env` 配置 `CLIPO_BACKUP_ALLOWED_ORIGINS=["http://minio:9000"]`，只对列出的精确 origin 放开内网/端口/HTTP。此设置与网页抓取无关，网页 SSRF 限制保持不变。HTTP 测试地址请勿用于跨不可信网络传输凭据。

下载副本默认保留 `CLIPO_EXPORT_RETENTION_DAYS=7` 天，过期返回“请重新导出”，本地目标与远端对象仍按各自保留策略存在。Docker API 与 worker 共用 `appdata` 卷，若更改本地路径，需额外挂载并保证 UID 10001 可写。

## 可复现验证

- `.venv/bin/pytest backend/tests/integration/test_backups.py backend/tests/integration/test_backup_targets.py`：临时 SQLite/模拟远端；加 `--postgres-url` 可在隔离 schema 中测试 PostgreSQL。
- `make build` 后运行 `uv run --no-project --with playwright python scripts/smoke_backup.py`：两个独立临时实例，浏览器导出、本地备份、空实例恢复、评论/标签/媒体链接与重复导入；`CLIPO_TEST_CHROMIUM` 可指定已安装 Chromium。
- `scripts/verify_backup_targets.py`：需要本机 59000 的 MinIO（测试用户 `clipo-test`、密码 `clipo-test-secret`）和 59001 的测试 WebDAV；只写测试 ZIP，不用于真实服务。验收服务、目录和容器在测试结束后由启动者清理。
