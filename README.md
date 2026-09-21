# Clipo

> 智能笔记应用，自动从小红书、小黑盒、网站等平台提取和整理内容

Clipo 是一个开源的自托管笔记应用，专注于从社交媒体和网站自动提取核心内容。通过 AI 智能总结和评论筛选，让你轻松保存和管理有价值的信息。

## 当前进度

已实现 [实施计划](IMPLEMENTATION_PLAN.md) 的 **Phase 2 核心链路**：保存公开网页、后台正文提取、AI 摘要与要点、笔记列表与详情、保存队列和失败重试，以及 PWA 分享入口。Phase 1 的账号、模型配置、API Token 和静态部署能力继续可用。

未配置模型或模型调用失败时，仍会保存原文，并显示“未生成摘要”。**Phase 3 平台专项**已提供小红书、小黑盒 Cookie 的加密配置与获取教程，并接入小红书 HTML 帖子与页面内嵌评论采集、评论初筛和 AI 评分。可在“内容采集”设置评论采集上限（0–100，默认 100，0 关闭），在模型设置中另行调整评分候选上限和高价值阈值；详情页展示本次采集上限、分数、理由和高价值标记，已采集但未评分的评论仍保留。小红书、小黑盒适配器与评分链路已通过离线夹具和用户提供的真实帖子/模型样本验收；小黑盒已支持官网帖子和分享链接，经官方接口提取正文、图片、作者、时间与顶层评论分页；独立登录有效性探测入口仍待接入。搜索、PWA 离线、扩展和备份按后续阶段推进。完整状态与验收限制见 [构建进度](docs/progress.md)。

## ✨ 目标特性（按阶段建设）

- **智能提取**：自动从小红书、小黑盒、网站、视频等平台抓取内容
- **AI 总结**：使用大语言模型智能总结核心信息
- **评论筛选**：自动识别和保存有价值的评论
- **多端支持**：PWA、浏览器扩展、iOS Shortcut 多种保存方式
- **自托管**：完全控制自己的数据和隐私
- **离线访问**：PWA 支持离线缓存，随时查看笔记
- **灵活备份**：支持本地导出、S3、WebDAV 多种备份方式

## 🚀 快速开始

### 使用 Docker Compose（推荐）

```bash
# 在仓库根目录生成 .env 和随机密钥（不会覆盖已有配置）
python3 scripts/init_env.py

# 从源码构建并启动应用与 PostgreSQL
docker compose up --build -d

# 访问 http://localhost:8000
```

首次访问会进入设置向导，按提示完成配置即可。

### 本地开发（无需 Docker）

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/)、Node.js 20+ 和 npm。

```bash
make install
make configure
make dev
```

访问 `http://localhost:3000`。默认使用 SQLite，API 运行在 8000 端口。执行 `make build && make serve` 可在 `http://localhost:8000` 检查与容器相同的静态托管模式。

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- 2GB+ 可用内存
- 10GB+ 磁盘空间（取决于保存的内容量）

## 📱 客户端规划

PWA 首版已提供；浏览器扩展和 Shortcut 仍为后续规划。

### PWA（Web App）

通过 HTTPS 访问服务（本机 localhost 可用 HTTP），在浏览器安装 Clipo：
- Android Chrome：安装后，从浏览器分享菜单选择 Clipo，自动保存公开网页。
- 桌面 / iOS：在首页粘贴链接保存；iOS Shortcut 将在 Phase 4 提供。
- 分享时未登录会先登录，再继续保存。当前阅读需要联网，离线能力将在 Phase 4 提供。

网页链接须使用 HTTP(S) 和 80/443 端口，拒绝内网地址。通用网页只支持公开静态 HTML；小红书支持 `/explore/帖子ID`、`/discovery/item/帖子ID` 和 `xhslink.com` / `xhslink.cn` 短链接，可在设置中填写 Cookie 后采集。小黑盒支持 `/app/bbs/link/帖子ID` 和官方 API 分享链接，最多采集 100 条顶层评论；小红书保留页面已有评论；配置完整 Cookie 并使用带访问参数的帖子链接时，按采集上限补抓顶层评论分页，不执行页面 JavaScript；设置仅对后续执行的任务生效，已有笔记不变。Android 系统分享面板仍需真机验收。

### 浏览器扩展

支持 Chrome、Edge 等 Chromium 浏览器：
1. 下载 `clipo-extension.zip`
2. 解压到本地目录
3. Chrome 设置 → 扩展程序 → 开发者模式 → 加载已解压的扩展程序
4. 在扩展设置中配置服务器地址和 API Token

详见 [浏览器扩展文档](docs/extension.md)

### iOS Shortcut

1. 导入后续发布的 `Clipo Shortcut` 文件
2. 编辑 Shortcut，填入服务器地址和 API Token
3. 在分享菜单中使用 Clipo Shortcut

详见 [iOS Shortcut 文档](docs/ios-shortcut.md)

## 📖 文档

- [构建进度](docs/progress.md) - 当前可用功能、验证结果与后续范围
- [技术架构](ARCHITECTURE.md) - 系统架构和技术选型
- [开发指南](DEVELOPMENT.md) - 开发环境搭建和实施计划
- [API 文档](docs/api.md) - RESTful API 参考
- [浏览器扩展](docs/extension.md) - 扩展开发和使用
- [iOS Shortcut](docs/ios-shortcut.md) - Shortcut 配置指南
- [配置参考](docs/configuration.md) - 详细配置说明
- [部署指南](docs/deployment.md) - 生产环境部署

## 🛠️ 技术栈

- **后端**: Python 3.11+ / FastAPI / PostgreSQL
- **前端**: React 18 / Next.js 14 / PWA
- **AI**: OpenAI 兼容 HTTP 客户端 / Pydantic 结构化校验
- **提取与队列**: trafilatura / readability / Huey（SQLite 持久化队列）
- **部署**: Docker / Docker Compose

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

在提交代码前，请确保：
- 代码通过 `make lint` 检查
- 测试通过 `make test`
- 更新相关文档

详见 [贡献指南](CONTRIBUTING.md)

## 📄 开源协议

本项目采用 [AGPL v3](LICENSE) 协议开源。

这意味着：
- ✅ 可以自由使用、修改、分发
- ✅ 可以用于商业目的
- ❗ 修改后的代码必须同样开源（包括网络服务）
- ❗ 必须保留原作者版权声明

## 🙏 致谢

- [DrissionPage](https://github.com/g1879/DrissionPage) - 强大的网页自动化工具
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用开发框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Python Web 框架

## 📧 联系方式

- Issues: [GitHub Issues](https://github.com/yourusername/clipo/issues)
- Discussions: [GitHub Discussions](https://github.com/yourusername/clipo/discussions)

---

**注意**：本项目为自托管应用，所有数据保存在你自己的服务器上。LLM API 费用由用户自行承担。
