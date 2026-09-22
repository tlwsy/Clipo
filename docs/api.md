# Clipo API 参考

基址 `/api/v1`。除注明外均需认证，请求与响应皆为 JSON，时间为 ISO 8601 UTC。可执行契约以 `/docs`、`/openapi.json` 和仓库的 `frontend/openapi.json` 为准。

当前 Phase 1–2 已实现元信息、初始化、认证、API Token、LLM 设置、网页采集、任务查询/重试、笔记查询/删除；Phase 3 新增平台 Cookie 配置及后台有效性检测，接入小红书、小黑盒、B 站与 YouTube。Phase 4 新增中文检索、标签与收藏；Shortcut 模板复用 API Token 和采集接口，本地契约验证已通过，iOS 实机待验收。内容直传、分享链接、导出和备份尚未提供。

## 认证与错误

| 方式 | 头部 | 适用 |
|------|------|------|
| Access JWT | `Authorization: Bearer <access_token>` | Web、移动客户端 |
| API Token | `X-Clipo-Token: <api_token>` | 脚本、后续扩展与 Shortcut |

```json
{ "error": { "code": "invalid_credentials", "message": "用户名或密码错误", "detail": {} } }
```

错误状态：400 参数错误、401 未认证、403 无权限、404 不存在、409 冲突、422 校验失败、500 内部错误、503 数据库不可用。校验错误的 `error.detail.fields` 提供字段、类型和可操作提示，不回显输入值。当前没有频控实现。

## 元信息与初始化

- `GET /health`：匿名，检查数据库连通性，返回 `{"status":"ok"}`。
- `GET /meta/version`：匿名，返回 `version`、`api_version`、`setup_completed`、`registration_open`。
- `GET /meta/capabilities`：返回 `capture_available: true`、`fulltext_search`（`sqlite_fts5`、`postgresql_bigm` 或 `postgresql_tsvector_like`）、`storage_backends: []`、`llm_configured`、`registration_open`。模型配置完整不代表连通性已经验证。
- `POST /setup/validate`：匿名，仅在初始化前可用。校验 `username`、`email`、`password`，成功返回 204，不创建账号。
- `POST /setup`：匿名，仅在初始化前可用；创建管理员，成功返回 201 和会话，之后返回 409。

```json
{
  "username": "reader",
  "email": "reader@example.com",
  "password": "a-long-password",
  "llm": {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-plus",
    "api_key": "sk-..."
  }
}
```

`llm` 可省略。用户名为 3–64 个字符，仅允许文字、数字、下划线和短横线，忽略大小写；邮箱必须有效；密码为 10–128 个字符。设置向导默认跳过 AI，之后可在设置页补充。

## 认证接口

- `POST /auth/register`：开放注册时创建账号，请求为用户名、邮箱和密码；关闭时返回 403。
- `POST /auth/login`：请求为 `username`、`password`，返回 `access_token`、`refresh_token`、`expires_in`、`user`。
- `POST /auth/refresh`：请求 `{"refresh_token":"rt_..."}`；轮换令牌，旧刷新令牌立即失效。
- `POST /auth/logout`：请求同刷新，撤销刷新令牌，返回 204。
- `GET /auth/me`：返回当前账号。

浏览器会收到 `clipo_refresh` Cookie（HttpOnly、SameSite=Strict、路径 `/api/v1/auth`，HTTPS 部署使用 Secure）。Web 的 Access Token 仅驻留内存，刷新/登出发送 `{}` 使用 Cookie。非浏览器客户端可显式提交刷新令牌。Access JWT 登出后在到期前仍有效，API Token 需另行撤销。

## API Token

- `GET /tokens`：列表，仅返回名称、时间，不返回明文。
- `POST /tokens`：请求 `{"name":"my-client"}`，返回 201 与 `id`、`name`、`token` 等；明文只显示一次。
- `DELETE /tokens/{id}`：撤销，返回 204。

## 采集

### POST /captures

请求 `{"url":"https://example.com/article"}`，返回 202。支持公开 HTTP(S) HTML 网页及已接入的平台帖子/视频链接，平台适配器按需查询官方数据接口；端口限 80/443；拒绝账号密码、内网地址、超大内容和非 HTML。可选 `payload` 用于浏览器内容直传，`selection` 位于其内部，具体见文末协议；不接受 `source_hint` 或其他未知字段。

可选请求头 `Idempotency-Key` 为 1–128 字符。相同用户、相同键和规范化 URL 返回同一任务；将同一个键用于不同 URL 返回 409。URL 规范化保留查询参数、移除 fragment。不同键可以生成多篇笔记，去重缓存用于复用提取结果。

```json
{
  "job_id": "j_0123456789abcdef0123456789abcdef",
  "url": "https://example.com/article",
  "status": "queued",
  "attempts": 0,
  "last_error": null,
  "note_id": null,
  "cached": false,
  "next_retry_at": null,
  "created_at": "2026-09-20T08:00:00Z",
  "updated_at": "2026-09-20T08:00:00Z"
}
```

任务先写入数据库，再分发到 Huey。`cached` 表示提取缓存命中；缓存按账号隔离，默认有效期 24 小时。

### GET /jobs · GET /jobs/{job_id}

列表支持 `?status=queued,running,retrying,failed,success&cursor=<opaque>&limit=50`，`limit` 为 1–100。返回 `{"items":[任务对象],"next_cursor":null}`。详情返回上面的任务对象，记录仅对所属账号可见。

状态流转：`queued → running → success`；暂时性抓取失败进入 `retrying → running`，自动重试 3 次后为 `failed`，最多执行 4 次。等待时间为 30 / 120 / 480 秒，`next_retry_at` 为下次时间。永久性错误直接失败。模型失败会保存原文，因此任务为 `success`，笔记为 `original_only`。

### POST /jobs/{job_id}/retry

仅失败任务可手动重试，返回 202 和任务对象；清零次数并重新入队。其他状态返回 409。删除任务记录的接口尚未提供。

## 笔记

### GET /notes

按创建时间倒序，支持 `?cursor=<opaque>&limit=50`，`limit` 为 1–100。支持 `q`（最多 200 字符，空白分隔的词需全部命中）、`tag_id` 与 `favorite=true/false` 组合筛选；列表和详情均含 `tags: [{id,name}]` 与 `is_favorite`。

```json
{
  "items": [{
    "id": 42,
    "title": "给未来的自己留一份知识笔记",
    "url": "https://example.com/article",
    "platform": "web",
    "author": "林舟",
    "summary_excerpt": "保留来源、压缩观点，并定期回顾。",
    "status": "ready",
    "created_at": "2026-09-20T08:01:00Z"
  }],
  "next_cursor": null
}
```

`summary_excerpt` 使用摘要或原文前 160 字。`status` 为 `ready` 或 `original_only`。

### GET /notes/{id}

返回 `id`、`title`、`url`、`source`、`content`、`summary_markdown`、`key_points`、`suggested_tags`、`comments`、`status`、`summary_error`、`created_at`、`updated_at`。

- `source`：平台、最终来源 URL、作者、作者 URL、发布时间；没有的元数据为 `null`。
- `content`：统一提取结构（URL、平台、标题、完整正文 `text`、作者、发布时间、图片 URL 和评论）。`comment_capture_limit` 记录本次平台评论采集上限（0–100，0 表示关闭），历史笔记和通用网页为 `null`。数据库保留原始 HTML，但接口的 `raw_html` 始终为 `null`。
- `summary_markdown`：AI 摘要；未生成时为 `null`，要点与建议标签为空数组。
- `summary_error`：未配置密钥或模型失败时的可读原因，不包含供应商原始返回或密钥。
- `comments`：小黑盒及视频适配器也按采集上限保存顶层评论/热评；小红书适配器按 `capture.max_comments` 保存页面内嵌的顶层评论（默认最多 100 条，含作者、内容、点赞及回复数），有完整 Cookie 和访问参数时补抓分页，不包含楼中楼内容。新增 `ai_score`（0–1 或 `null`）、`ai_reason`（理由或 `null`）与 `is_valuable`（评分达到采集时阈值）。初筛只选择评分候选，已采集评论全部保留且保持原始顺序；未评分不等于 0 分。通用网页提取器不提取评论。
- `comment_score_error`：评论评分失败原因；无评分错误或历史笔记为 `null`。有效摘要不会因评分失败而丢失。
- `content.capture_warnings`：采集未完整完成的可读提示，例如分页缺少 Cookie/访问参数、分页预算耗尽；不会回显平台返回体。`extractor_version` 供缓存版本判定使用。

图片目前只保留来源链接，不下载媒体。AI 建议会自动添加为标签；`suggested_tags` 保留模型原始建议，`tags` 为当前可管理标签。

### DELETE /notes/{id}

返回 204，删除笔记、来源和评论。任务记录保留，`note_id` 变为 `null`；已删除或不属于当前账号的笔记返回 404。

### 标签与收藏

- `PATCH /notes/{id}`：`{"is_favorite":true}`，返回更新后详情。
- `GET /tags`：当前账号全部标签。
- `POST /notes/{id}/tags`：`{"name":"知识管理"}`，返回标签。名称 1–50 字符、折叠空白；相同名称和重复关联幂等。
- `DELETE /notes/{id}/tags/{tag_id}`：仅移除该笔记关联，可重复调用。
- `DELETE /tags/{tag_id}`：删除当前账号标签及其所有关联，保留笔记。

迁移 `0006_note_organization` 为已有笔记的 AI 建议补建标签，回滚保留笔记和原始建议，移除收藏及可管理标签。

## 设置

`GET /settings` 返回 `llm`、`capture` 与 `platform_cookies`。`capture` 包含 `max_comments`（默认 100）；`llm` 包含 `base_url`、`model`、`api_key_set`、`comment_score_threshold`、`max_comments`、`text_token_budget`、`overridden_fields`；`platform_cookies` 只返回保存状态：

```json
{"xiaohongshu":{"cookie_set":false},"xiaoheihe":{"cookie_set":false}}
```

`cookie_set: true` 仅表示存在已加密的配置，不代表平台登录有效。接口不返回 Cookie 明文或密文。

`PUT /settings` 请求示例：

```json
{"llm":{"base_url":"https://api.deepseek.com/v1","model":"deepseek-chat","api_key":"sk-...","text_token_budget":8000}}
```

省略字段保留原值；传 `null` 恢复默认或清除密钥。模型配置按环境变量 > 用户数据库 > 默认值生效，读接口不返回密钥。正文预算按 UTF-8 字节保守估算，仅截断送给模型的内容。`max_comments`（1–100，默认 30）控制评论初筛后的候选数量，`comment_score_threshold`（0–1，默认 0.6）控制高价值标记。评论输入还受字节预算限制；配置在任务执行时读取，已有笔记不自动重算。连通性测试接口尚未实现。

评论采集使用同一 `PUT /settings` 接口，独立于 `llm.max_comments`：

```json
{"capture":{"max_comments":10}}
```

`capture.max_comments` 只接受 0–100 的整数，0 表示关闭评论采集，`null` 恢复默认 100；省略整个 `capture`、传 `null` 或 `{}` 均保留原配置。`capture` 内未知字段返回 422。修改按账号隔离，参数非法时同次请求的所有配置均不落库。

小红书、小黑盒、B 站、YouTube 后台任务执行时读取采集上限，先采集再按 LLM 候选上限评分。命中缓存时按当前上限裁剪副本；如果当前上限大于缓存记录的原采集上限，会重新抓取，此时 `cached` 为 `false`。分页接入前的旧缓存会失效以重新抓取。现有笔记不变；关闭采集不删除完整 HTML 快照或已有缓存。

平台 Cookie 使用同一 `PUT /settings` 接口：

```json
{"platform_cookies":{"xiaohongshu":"name=value; name2=value2","xiaoheihe":null}}
```

仅支持 `xiaohongshu` 和 `xiaoheihe`，未知平台返回 422。各平台省略则保留原值，字符串替换，`null` 或空字符串清除；省略整个 `platform_cookies`、传 `null` 或 `{}` 均不修改 Cookie。Web 表单留空会省略该平台字段，勾选清除才发送 `null`。Cookie 为请求头的值，不能带 `Cookie:` 前缀或控制字符，最多 16384 个可打印 ASCII 字符，格式为 `name=value; name2=value2`。参数非法时整次请求不落库，包括同次提交的 LLM 配置。

Cookie 通过当前账号的仓储加密保存；保存设置不向平台发起请求。小红书采集任务在执行时读取当前账号 Cookie，限制发送到官方 HTTPS 主机；登录页/401 会提示更新 Cookie，429 自动退避，未知结构直接失败。小黑盒采集也读取当前账号 Cookie，使用官方 API 签名分页；独立检测通过下述后台检测接口发起。采集成功不会将 `cookie_set` 解释为登录已验证，也不会更新单独的登录状态。


### 平台登录有效性检测

`GET /settings/platform-checks` 返回当前账号的 `xiaohongshu` / `xiaoheihe` 状态，每项含 `status`、`message`、`requested_at`、`checked_at`。状态为 `unconfigured`（未配置）、`unverified`（未检测）、`queued`、`running`、`valid`、`invalid` 或 `error`（网络/验证/结构等原因，无法确认）。不会返回账号身份、Cookie、凭据摘要或签名。

`POST /settings/platform-checks/{platform}` 返回 202 和该平台检测状态；只接受 `xiaohongshu` / `xiaoheihe`。未保存 Cookie 返回 409。请求提交事务后入队，重复检测中的请求共用检测记录；worker 恢复漏投递与过期的 3 分钟租约，连续 3 次执行中断后提示重试。任务参数仅有账号 ID、平台与随机请求 ID。明确身份成功才标记 valid；风控、验证码、频控和网络失败不误报 Cookie 失效。

结果只对当前加密凭据版本有效，更换或清除 Cookie 会清除对应检测记录。任务结果同时校验账号、请求、执行标识和凭据版本，迟到结果不能覆盖新配置；valid 仅代表检测时间点有效。

## 后续接口规划

Phase 4 的 `q` 搜索、标签与收藏接口已提供，Shortcut 复用现有 `POST /captures`。Phase 5 已扩展 `POST /captures` 的内容直传与分块上传（见下文）；Phase 6 计划接入导出、导入与备份。分享链接、重新摘要、删除任务、限流等额外接口尚未实现，请勿依赖此前规划中的示例端点。

## iOS Shortcut 自动配置

- `GET /shortcuts/info`：公开返回通用指令名称 `保存到 Clipo`、协议版本 `1`、未签名模板地址和可选的 iCloud 安装链接。未配置安装链接时为 `null`，不使用包含个人凭据的分享链接。
- `GET /shortcuts/template`：公开下载可复现、无凭据的未签名 `.shortcut`。仍需 Apple 签名/导入与文件动作实机验证。
- `POST /shortcuts/pairings`：需登录，请求 `{"name":"我的 iPhone","server_url":"https://clipo.example.com"}`。返回 201，含 `id`、`expires_at`、`status`、`token_id`、`setup_input` 和 `launch_url`。地址由用户当前浏览器 origin 提供，不信任 Host/代理头，也不会由后端请求；不允许路径、查询、片段或 URL 凭据。公网须 HTTPS，HTTP 只允许本机/内网 IP 测试（可带端口）。不创建 Token，5 分钟内领取才签发。
- `GET /shortcuts/pairings/{id}`：仅本账号可查，状态为 `pending`、`expired`、`claimed` 或 `revoked`，不返回配置码、启动链接或 Token。`claimed` 仅表示已签发凭据，不证明手机已保存配置文件。
- `DELETE /shortcuts/pairings/{id}`：取消本账号未领取的配置；已领取时返回 409，应通过已有 Token 接口撤销设备访问。
- `POST /shortcuts/pairings/consume`：以 JSON `{"code":"cp_…"}` 提交一次性配置码，无需浏览器登录；返回 `{version:1,server_url,token,token_id}`。无效、过期、已使用或已替换均返回 400 `pairing_unavailable`，响应不会回显配置码。

每账号只保留一条最新配置记录，生成新码会原子替换旧码，已签发设备 Token 保留，须单独撤销。配置码为 256 位随机值，仅存 SHA-256；领取以账号和摘要限定的条件 UPDATE 实现，消费与 Token 创建同一事务，支持 SQLite/PostgreSQL。竞争领取只成功一次，响应丢失后应重新生成配置并在 Token 列表撤销不用的令牌。所有响应使用 `Cache-Control: no-store`。

`launch_url` 使用 Apple `shortcuts://run-shortcut` 的文本输入协议，输入为 `clipo-setup:` 加 JSON（`version`、`server_url`、`code`）。公共模板将成功领取的 JSON 保存为 iCloud Drive 的 `Shortcuts/Clipo.json`；平常优先提取分享输入的首个 URL，无分享输入时读取剪贴板，然后使用文件中的地址和 Token 提交采集。配置文件可能随 iCloud 同步，不应分享文件内容。

## 浏览器内容直传（Phase 5）

`POST /api/v1/captures` 仍接受 `{ "url": "https://example.com/article" }`。
扩展可增加 `payload`：`title`、`text` 必填；可选 `author`（字符串）、`author_url`、
`published_at`（ISO 时间）、`images`、`comments`（author/content/likes/replies）、
`selection`、`tags`、`capture_warnings`。精确长度限制见生成的 OpenAPI。
不接受 Cookie、任意 HTML 或模型评分。URL 仍限定公开 HTTP(S) 地址；直传分支不解析 DNS、
不请求目标网站，不读写网页提取缓存。worker 按执行时账号配置裁剪评论后生成摘要和评分。

单次请求最多 5 MiB（包含 JSON 包装）。更大的 payload 使用以下协议，总量最多 20 MiB：

1. 将 **payload 对象本身**编码为 UTF-8 JSON，计算字节数与 SHA-256。
2. `POST /api/v1/captures/uploads`，JSON 为 `url`、`total_bytes`、`sha256`，
   附 `Idempotency-Key`；返回 `status=uploading` 的任务，此时不入队。
3. `PUT /api/v1/captures/{job_id}/chunks/{position}`，从 0 开始顺序编号，
   body 为二进制分块。每块 256 KiB，最后一块为剩余字节；同内容重复 PUT 安全。
4. `POST /api/v1/captures/{job_id}/complete`，校验完整性、摘要与结构后才入队。
   重复完成返回同一任务。读取任务仍使用 `GET /api/v1/jobs/{job_id}`。

所有操作均需 JWT 或 `X-Clipo-Token` 并隔离账号。上传有效期 1 小时，worker 定期清理过期分块，
失败任务需从扩展重新保存。相同幂等键配不同 URL/内容/上传描述返回 409。
代理需允许至少 5 MiB 的请求体（Nginx 可设 `client_max_body_size 6m`）。
