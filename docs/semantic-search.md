# AI 语义搜索

本阶段在原有全文搜索之外增加按含义查找笔记的能力。迁移为 `0019_semantic_search`，
向量与后台任务均按账号隔离，不进入公开分享或资料库备份。当前后端已经接入，
搜索页与设置交互、浏览器验收和本机 Compose 升级继续在后续节点完成。

## 模型与费用

- 默认关闭。通过 `PUT /api/v1/settings` 的 `llm.embedding_enabled` 开启，
  `llm.embedding_model` 指定嵌入模型（默认 `text-embedding-3-small`）。
- 复用当前账号的模型 Base URL 和加密保存的 API Key，也遵循部署环境覆盖设置。
  聊天模型不一定提供嵌入接口；服务必须支持 `POST /embeddings`、`encoding_format: float`
  及 `dimensions: 1536`，并返回一个有效的 1536 维向量。可更换模型名，暂不支持其他维数。
- 开启后会自动为已有笔记补齐向量，产生模型调用费用。笔记输入是标题、摘要和要点，
  按 UTF-8 限制在 8000 字节以内，不包含私人批注、评论、Cookie 或完整原文。
  没有摘要的笔记使用标题；成功重新生成摘要后会更新向量。
- 搜索问题同样会发送到已配置的模型服务。查询及查询向量仅在当前账号/模型下缓存 10 分钟，
  到期后不再使用，由请求或 worker 定期清理；查询缓存不导出、不公开。

## 搜索 API

- `GET /api/v1/notes/search?q=如何提高专注力&mode=auto&limit=30`
- `GET /api/v1/notes/search/semantic?q=如何提高专注力&limit=20`（仅语义候选）
- 两者均支持 `tag_id`、`favorite` 和 `collection_id`，每一层都检查账号归属。
- `mode` 为 `auto`、`semantic` 或 `fulltext`。自动模式使用本地规则：引号包围的精确短语
  走全文；较长问题（至少 12 字符）、至少三个词或包含“如何/关系/影响”等问题词时使用语义，
  其余走全文。规则不是语言理解模型，可用 API 参数强制选择。
- 自动模式的自然语言查询和强制 `semantic` 模式合并语义 top 20、全文 top 10，
  使用 `k=60` 的 RRF 按名次融合并去重，返回最多 30 条。`score` 是归一化排序分数，
  不是置信概率；`similarity` 为余弦相似度。匹配类型为 `semantic`、`fulltext` 或 `both`。
- 首次查询由 worker 生成向量，HTTP 请求不调用模型。`semantic_status` 表示状态，
  `retry_after` 表示建议轮询间隔；等待、未配置或失败时混合端点保留关键词候选并返回说明。
  `/search/semantic` 不补入关键词候选。原有 `/notes?q=...` 的全文检索及分页保持可用。
- 每账号每分钟最多 120 次搜索请求，配额跨 API 进程共享。API 与浏览器不缓存私有响应。

## 补齐与恢复

`GET /api/v1/settings/search-index` 提供当前模型的总量、已完成、待处理、异常数量、补齐状态。
异常数包含正在自动重试的笔记，因此可能与待处理数重叠。异常比例可以由 `failed / total` 监控。
`POST /api/v1/settings/search-index` 重新扫描缺失或失败的索引，也清除失败的查询缓存，
每账号每分钟最多三次。已有且有效的向量不会重复收费。

- 后台按每批 50 篇扫描，游标持久化；新采集、成功重新摘要和恢复的笔记会在同一事务写入任务。
- 提交后入队，漏分发及失去执行租约的任务由 worker 启动和每分钟恢复，租约为 90 秒。
  执行 ID 和任务代次阻止过期 worker 覆盖新结果；删除笔记级联清除相关任务。
- 笔记失败最多自动重试三次（30/120/480 秒），查询失败最多重试两次（2/5 秒）。
  错误信息固定，不记录供应商返回体、密钥或输入文本。模型不可用不影响采集原文或已有摘要。
- 模型名或 Base URL 改变后旧向量立即排除，后台按新模型补齐；更换密钥也会启动补齐/失败恢复。
  关闭功能阻止新调用，在途调用可能已发送，但结果不会继续应用。
- 部署环境变量改变需重启 API/worker，并提交一次补齐请求；两者必须共享模型覆盖设置。
- 备份仅保存原始笔记资料，不携带向量或查询缓存。恢复到开启语义搜索的账号后重新生成向量。

## PostgreSQL 与 SQLite

PostgreSQL 16 需要 pgvector 0.8+。迁移在 `public` 安装 `vector` 扩展，数据库角色需要对应权限，
否则应先由管理员在应用数据库执行 `CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public`。
回滚移除本功能字段和任务表，保留笔记及可能被其他应用使用的扩展。

计划中的 IVFFlat 示例依赖已有样本训练；本实现采用可在空库创建的 HNSW 余弦索引，适合渐进补齐。
查询开启严格顺序的迭代扫描以处理账号、标签和空间过滤；候选不足时用精确扫描补齐。
HNSW 仍是近似检索，大规模数据的召回率、延迟与成本尚需实际负载评估。
SQLite 用 JSON 保存向量并流式精确计算余弦相似度，适合本地开发和小型资料库，没有向量索引加速。

Compose 的数据库镜像由 `deploy/postgres.Dockerfile` 构建，保持原来的 `postgres:16-alpine`
运行环境，在构建阶段加入固定并校验源码摘要的 pgvector 0.8.2；无需新增服务或 Redis。
升级本分支的本机测试环境可运行：

```bash
CLIPO_IMAGE=clipo-app docker compose build db app
CLIPO_IMAGE=clipo-app docker compose up -d --no-build --wait --wait-timeout 120
docker compose ps
```

仅执行旧的 `docker compose build app` 不会给数据库安装扩展。外部 PostgreSQL 部署需自行安装扩展包。
本分支尚未发布公共应用镜像，仓库默认 GHCR 镜像不代表已包含本阶段代码。

## 验证边界

单元和集成测试使用固定向量、临时 SQLite/隔离 PostgreSQL schema，覆盖协议、过滤、账号隔离、
租约、重试、代次保护、批量补齐、摘要刷新、备份恢复和升级/回滚。它们不证明真实模型语义质量、
供应商兼容性、真实额度与大规模性能；本次未调用真实嵌入服务。逐节点运行结果见 [进度](progress.md)。
