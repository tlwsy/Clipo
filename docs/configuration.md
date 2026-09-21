# 配置参考

Clipo 有两层配置：**环境变量**（部署级，优先级最高）与**数据库配置**（用户级，在设置页维护）。同名项环境变量覆盖数据库值。

当前 Phase 1–2 已实现基础、数据库、队列、通用网页提取和 LLM 配置；Phase 3 已提供平台 Cookie 的加密保存、替换与清除，尚未用于抓取。媒体和备份部分为后续规划。实际部署模板见仓库根目录的 [`.env.example`](../.env.example)，执行 `make configure` 可生成带随机密钥的 `.env`。

## 环境变量

### 基础

| 变量 | 默认 | 说明 |
|------|------|------|
| `CLIPO_SECRET_KEY` | 无，必填 | JWT 签名与字段加密主密钥，建议 `openssl rand -hex 32` |
| `CLIPO_BASE_URL` | `http://localhost:8000` | 对外访问地址，用于生成分享链接 |
| `CLIPO_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CLIPO_REGISTRATION_OPEN` | `false` | 是否开放自助注册 |
| `CLIPO_TIMEZONE` | `Asia/Shanghai` | 影响定时备份的执行时刻 |

更换 `CLIPO_SECRET_KEY` 会导致已加密的 LLM Key 与 Cookie 无法解密，需在设置页重新填写。

主密钥至少 32 个字符，缺失或过短时应用拒绝启动。`CLIPO_BASE_URL` 为 HTTPS 时刷新 Cookie 会设置 Secure；使用 HTTPS 反向代理时必须填写实际的 HTTPS 地址。

### 数据库

| 变量 | 默认 | 说明 |
|------|------|------|
| `CLIPO_DATABASE_URL` | `sqlite:///./data/clipo.db` | PostgreSQL 示例：`postgresql+psycopg://clipo:pw@db:5432/clipo` |
| `CLIPO_DB_POOL_SIZE` | `5` | 仅 PostgreSQL 生效 |

单用户轻量部署可用 SQLite；多用户或需要中文分词检索时用 PostgreSQL。

### 任务与抓取

| 变量 | 默认 | 说明 |
|------|------|------|
| `CLIPO_QUEUE_PATH` | 仓库 `data/huey.db` | Huey 的 SQLite 队列文件，API 与 worker 必须共用；容器为 `/app/data/huey.db` |
| `CLIPO_EXTRACTION_CACHE_TTL_SECONDS` | `86400` | 按账号隔离的提取缓存有效期，0 禁用，最大 30 天 |

当前固定使用两个 worker 线程，自动重试 3 次（30 / 120 / 480 秒）；HTTP 每次操作超时 20 秒，读取总时限 60 秒，最多 5 次重定向、5 MB HTML。仅支持 HTTP(S) 的 80/443 端口，始终拒绝内网地址。尚未开放抓取浏览器和上述限制的环境覆盖开关。

### 存储（后续规划）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CLIPO_MEDIA_BACKEND` | `local` | `local` / `s3` |
| `CLIPO_MEDIA_PATH` | `./data/media` | 本地存储根目录 |
| `CLIPO_S3_ENDPOINT` | 空 | 如 `https://oss-cn-hangzhou.aliyuncs.com` |
| `CLIPO_S3_BUCKET` / `CLIPO_S3_ACCESS_KEY` / `CLIPO_S3_SECRET_KEY` | 空 | S3 兼容凭据 |
| `CLIPO_S3_REGION` | `cn-hangzhou` | 区域 |

## 用户级配置（设置页）

### LLM

| 项 | 说明 |
|----|------|
| Base URL | OpenAI 兼容端点。直连模型服务或指向自建 One API 网关 |
| API Key | 加密存储，读接口只返回是否已设置 |
| 模型 | 如 `qwen-plus`、`glm-4`、`deepseek-chat` |
| 评论评分阈值 | 默认 0.6，字段已保存，Phase 3 接入评分 |
| 候选评论上限 | 默认 30，Phase 3 接入评论筛选 |
| 正文 token 预算 | 默认 8000；按 UTF-8 字节数保守估算，中文通常保留更少正文；只截断模型输入，原文完整保留 |

常见端点（填入 Base URL 即可，Clipo 只要求 OpenAI 兼容）：

```
通义千问   https://dashscope.aliyuncs.com/compatible-mode/v1
智谱 GLM   https://open.bigmodel.cn/api/paas/v4
DeepSeek   https://api.deepseek.com/v1
One API    http://your-one-api:3000/v1
```

未配置 LLM 时 Clipo 仍可保存原文，只是不生成摘要与评论评分。

Phase 2 已调用模型并生成摘要、要点与建议标签；标签管理和评论评分在后续阶段提供。模型首次请求使用 JSON mode，失败后兼容普通 JSON 输出重试一次，再降级保存原文。部署者可以使用 `CLIPO_LLM_BASE_URL`、`CLIPO_LLM_MODEL` 和 `CLIPO_LLM_API_KEY` 覆盖用户数据库设置，环境覆盖字段会在 Web 设置页锁定。未配置这些变量时由用户设置决定；不要保留值为空的覆盖变量，除非确实要覆盖为空。`CLIPO_LLM_API_KEY` 若设置为空，会禁用已保存的用户密钥。

### 平台 Cookie

设置页的“平台 Cookie”区域支持小红书和小黑盒。每个平台独立保存，按当前 Clipo 账号隔离，沿用 `CLIPO_SECRET_KEY` 加密；接口只返回是否已配置，不返回明文或密文。当前尚未接入平台采集与登录有效性探测，页面显示“已保存，未验证”，保存操作不会向平台发送请求。

获取步骤（设置页也可展开对应平台教程）：

1. 在桌面浏览器登录[小红书](https://www.xiaohongshu.com)或[小黑盒](https://www.xiaoheihe.cn)。
2. 打开开发者工具 → Network（网络），刷新页面并选择该平台的请求。
3. 在 Request Headers（请求标头）中复制 `Cookie` 的值，例如 `name=value; name2=value2`。不要复制 `Cookie:` 前缀、响应的 `Set-Cookie`、整个请求或多行文本。
4. 粘贴到 Clipo 设置页对应平台的输入框，点击“保存平台配置”。Cookie 最多 16384 个字符，仅接受可打印 ASCII 字符与有效的名称/值格式。

保存成功后输入框清空；留空会保留原值，填写新值会替换，勾选“清除”再保存会移除对应平台 Cookie。保存失败时保留输入，便于重试。Cookie 代表平台登录身份，请勿分享或提交到仓库。

Cookie 有效性探测、登录失效诊断将随 Phase 3 平台适配器接入；Phase 5 的浏览器扩展将提供 DOM 直取路径。当前没有“测试 Cookie”接口，也不保证所保存的 Cookie 仍然有效。

### 媒体策略（后续规划）

| 取值 | 行为 |
|------|------|
| `url_only` | 只存原图链接，最省空间，原站删图后失效 |
| `thumbnail_only`（默认） | 下载缩略图用于列表，原图存链接 |
| `full` | 下载原图，永久可用，占用空间大 |

### 备份（后续规划）

| 项 | 说明 |
|----|------|
| 目标 | `none` / `local` / `s3` / `webdav` |
| 计划 | Cron 表达式，如 `0 4 * * *` 表示每日 04:00 |
| 内容 | 完整 JSON + Markdown 目录，可选含媒体文件 |
| 保留份数 | 默认 7，超出自动清理最旧的 |

WebDAV 需要填写地址、用户名、密码，例如坚果云的 `https://dav.jianguoyun.com/dav/`。

## .env.example

```dotenv
# 必填
CLIPO_SECRET_KEY=
CLIPO_BASE_URL=http://localhost:8000

# 数据库（二选一）
CLIPO_DATABASE_URL=postgresql+psycopg://clipo:clipo@db:5432/clipo
# CLIPO_DATABASE_URL=sqlite:///./data/clipo.db

# 运行
CLIPO_LOG_LEVEL=INFO
CLIPO_REGISTRATION_OPEN=false
CLIPO_QUEUE_PATH=./data/huey.db
CLIPO_EXTRACTION_CACHE_TTL_SECONDS=86400

# PostgreSQL 容器
POSTGRES_USER=clipo
POSTGRES_PASSWORD=clipo
POSTGRES_DB=clipo
```

LLM Key 与平台 Cookie 不放在 `.env`，在设置页填写，以便加密存储与按用户隔离。
