# Clipo 贡献指南

感谢你关注并愿意为 Clipo 贡献力量！Clipo 采用 **[AGPL-3.0](LICENSE)** 协议开源。无论你的贡献是报告缺陷、补充文档、优化前端界面，还是为 Clipo 添加新的社交媒体与内容平台适配器，我们都表示衷心的欢迎和感谢。

提交代码即代表你同意以 AGPL-3.0 协议向开源社区授权你的贡献。

---

## 目录

- [贡献方式](#贡献方式)
- [开始之前](#开始之前)
- [开发工作流](#开发工作流)
- [核心贡献指南：添加新的平台适配器](#核心贡献指南添加新的平台适配器)
- [代码与质量规范](#代码与质量规范)
- [PR 提交清单 (Checklist)](#pr-提交清单-checklist)
- [Bug 报告与反馈](#bug-报告与反馈)
- [安全问题披露](#安全问题披露)
- [行为准则](#行为准则)

---

## 贡献方式

你可以通过以下形式参与 Clipo 的建设：

1. 🐛 **报告 Bug**：发现功能异常或平台改版导致提取失效，通过 GitHub Issues 反馈详细复现路径。
2. 💡 **提出建议**：提出新功能构想或体验优化建议。
3. 📖 **改进文档**：修正拼写错误、完善部署说明或补充使用案例。
4. 🔌 **新增平台适配器**：为流行平台（资讯社区、技术博客、社交媒体等）编写专用提取器。
5. 💻 **提交代码修复与新功能**：改进后端服务、优化前端交互或完善浏览器扩展。

---

## 开始之前

在着手编写复杂代码前：
- 建议先通读 [系统架构 (ARCHITECTURE.md)](ARCHITECTURE.md) 与 [开发指南 (DEVELOPMENT.md)](DEVELOPMENT.md)，了解 Clipo 的核心设计思路与本地开发流程。
- 如果是大型改动或重构，建议先在 GitHub Issues 或 Discussions 中发起讨论，与维护者对齐设计方案，避免耗费精力后发现与核心架构冲突。
- 小型修复、文档完善或新增平台适配器可以直接提交 Pull Request。

---

## 开发工作流

1. **Fork 仓库** 到你自己的 GitHub 账号下，并克隆到本地：
   ```bash
   git clone https://github.com/<your-username>/Clipo.git
   cd Clipo
   ```

2. **从 `main` 分支创建功能分支**：
   ```bash
   git checkout -b feat/add-xyz-extractor   # 新功能
   # 或
   git checkout -b fix/issue-description   # 修复 Bug
   ```

3. **配置本地开发环境**：
   ```bash
   make install     # 安装后端与前端依赖
   make configure   # 生成本地配置文件与随机密钥
   make dev         # 启动本地开发服务 (API 8000 / 前端 3000)
   ```

4. **编写代码与针对性测试**（请务必遵循下文的离线测试规范）。

5. **本地质量门禁验证**：
   ```bash
   make lint        # 代码规范检查 (Ruff, Black, ESLint, TypeScript)
   make test        # 后端与前端自动化测试
   ```

6. **提交代码 (Git Commit)**：
   提交信息需遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范，例如：
   - `feat(extractor): add weibo article adapter`
   - `fix(sharing): resolve token expiration edge case`
   - `docs(readme): clarify docker deployment steps`

7. **推送分支并创建 Pull Request**，按照模板清晰描述改动背景、实现方式与验证结果。

---

## 核心贡献指南：添加新的平台适配器

现代社交媒体与内容平台的页面结构演进频繁，**新增与维护平台适配器（Extractor）是社区中最有价值的贡献之一**。

新增适配器的完整步骤如下：

### 1. 适配器接口契约
在 `backend/app/extractors/` 目录下新建适配器文件（例如 `weibo.py`），实现 `Extractor` 协议：
```python
from app.extractors.base import CapturedContent

class WeiboExtractor:
    name: str = "weibo"

    def matches(self, url: str) -> bool:
        """判断给定的 URL 是否应由当前适配器处理。"""
        ...

    def extract(self, url: str, payload: dict | None = None) -> CapturedContent:
        """从页面提取结构化数据，返回统一的 CapturedContent。"""
        ...
```

### 2. 字段原则：宁缺毋滥，拒绝猜测
- `CapturedContent` 包含标题、正文、作者、发布时间、图片链接、评论列表等字段。
- **缺失字段请保留为 `None` 或空列表**，绝对不要使用推测值或默认占位符填充。下游的 AI 提炼和归档更在乎数据的真实性。

### 3. 注册适配器
在 `backend/app/extractors/registry.py` 中注册新适配器。
> **注意**：专用适配器必须注册在通用适配器（`GenericExtractor`）**之前**，否则会被通用正文提取引擎拦截。

### 4. 离线测试夹具（硬性要求 ⚠️）
**自动化测试绝对不允许发起真实的外部网络请求！**
- 真实外部请求会导致 CI 依赖外网环境，且一旦平台风控或页面变动就会导致构建爆红。
- 你必须在 `backend/tests/fixtures/` 下放置脱敏的离线 HTML 样本（例如 `weibo_article.html`）。
- 在 `backend/tests/unit/test_extraction.py` 中编写单元测试，加载离线 HTML 夹具并断言字段提取准确性。

### 5. 跨域安全与 SSRF 防护
如果适配器需要服务端发起网络请求：
- 必须使用项目现有的安全请求工具，严格遵守系统内置的 SSRF 防护机制（仅允许 HTTP(S) 80/443、拦截内网 IP、逐次校验重定向与 DNS 结果）。
- 如果涉及平台 Cookie，必须通过用户设置安全加载，并严格限制 Cookie 发送的域名范围与 HTTPS 协议，禁止跨站泄露。

---

## 代码与质量规范

### 后端代码规范 (Python)
- 遵循 Python 3.11+ 标准，使用 **Ruff** 和 **Black** 进行检查与格式化，单行最大宽度为 **100**。
- 所有新增函数和公共接口必须具备**完整的类型注解**（包含参数与显式返回类型）。
- 路由层（`backend/app/api/`）只负责参数校验与服务调用，不要在路由中直接编写复杂的业务逻辑。
- 业务异常统一继承 `ClipoError`，由全局统一异常处理器转为标准的 `{ "error": { "code": "...", "message": "..." } }` 格式。

### 严格的租户与数据隔离
- Clipo 虽为自托管应用，但原生支持多账户/多设备。
- **所有涉及用户数据的查询和写入必须经过仓储层（Repository）显式限定 `user_id`**，绝对禁止在服务层或路由层进行裸写跨用户查询，杜绝横向越权。

### 前端代码规范 (TypeScript / Next.js)
- 启用 TypeScript 严格模式。
- **严禁手动手写后端 API 接口契约**。修改后端 Schema 或接口后，必须运行 `make gen-api`，由 OpenAPI 自动生成 `frontend/lib/api-types.ts` 并一并提交。
- Access Token 仅在浏览器内存中持有，Refresh Token 使用 `HttpOnly` Cookie，保持并发请求的续期协调逻辑。

### 开源许可证头声明
- 新增的代码源文件（`.py`, `.ts`, `.tsx`, `.mjs` 等）建议在文件顶部添加 SPDX 规范标识：
  ```
  # SPDX-License-Identifier: AGPL-3.0-or-later
  ```

---

## PR 提交清单 (Checklist)

在发起 Pull Request 前，请逐项自查：

- [ ] 本地已运行 `make lint` 且无任何报错
- [ ] 本地已运行 `make test`，所有自动化测试通过
- [ ] 若修改了后端 API 契约，已执行 `make gen-api` 并一并提交了更新后的生成文件
- [ ] 若新增或修改了平台适配器，已提供 `tests/fixtures/` 下的离线测试夹具，且测试中**没有**发起任何真实外部网络请求
- [ ] 新建或修改的方法均带有清晰的类型注解
- [ ] 数据访问通过仓储层严格限定了 `user_id`
- [ ] 代码中**绝无**硬编码的个人密钥、实际 Cookie、API Token 或测试产生的真实个人数据
- [ ] 相关的文档（如 `docs/` 或 `README.md`）已同步更新

---

## Bug 报告与反馈

发现 Bug 时，请前往 [GitHub Issues](https://github.com/tlwsy/Clipo/issues) 提交工单，并尽可能提供以下信息：

1. **Clipo 版本**：如 `v0.1.0` 或 Git Commit 哈希。
2. **部署环境**：如 Docker Compose、源码部署、操作系统版本。
3. **数据库类型**：PostgreSQL 16 或 SQLite。
4. **复现步骤**：简洁明了的步骤说明。
5. **日志与错误堆栈**：请将报错信息完整贴出。**注意：日志中的 API Key、Cookie、用户 Token 在粘贴前请务必仔细检查并脱敏！**
6. **涉及特定网页抓取时**：可附上无法抓取的公开页面 URL 类型（无需私密或敏感内容）。

---

## 安全问题披露

如果你在 Clipo 中发现了安全漏洞（例如认证绕过、SSRF 绕过、越权访问、凭据泄露等）：

- **请不要在公开的 GitHub Issue 或 Discussions 中披露漏洞详情！**
- 请通过 GitHub Security Advisories 私密通道提交，或发送私密邮件联系项目维护者。
- 维护者将优先评估与修复，待修复补丁发布后共同协商适当时机公开。

---

## 行为准则

我们致力于营造一个友善、包容且高效的技术交流氛围：
- 尊重每一位贡献者与社区成员的时间与劳动；
- 坚持就事论事，友好沟通；面对技术路线分歧时，讲清技术论据和权衡考量比争论输赢更有价值。
