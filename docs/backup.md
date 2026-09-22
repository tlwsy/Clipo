# 备份与恢复

备份以当前账号的笔记库为单位，包括笔记原文和 HTML 快照、摘要与要点、来源、评论及评分、标签（含未关联标签）、收藏状态、创建/修改时间与图片链接。账号、登录令牌、模型密钥、平台 Cookie、运行队列及提取缓存不在导出范围。当前媒体仅保存外链，备份恢复媒体引用，不会下载图片文件。

## 导出和导入

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
