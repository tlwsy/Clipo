# 贡献指南

欢迎 Issue 与 Pull Request。项目采用 AGPL v3，提交代码即表示同意以该协议授权。

## 开始之前

读一遍 [ARCHITECTURE.md](ARCHITECTURE.md) 与 [DEVELOPMENT.md](DEVELOPMENT.md)。前者说明为什么这样设计，后者说明怎么跑起来。

较大的改动先开 Issue 讨论方向，避免写完才发现和整体设计冲突。小修小补直接提 PR 即可。

## 提交 PR

1. 从 `main` 切分支：功能 `feat/xxx`，修复 `fix/xxx`。
2. `make lint` 与 `make test` 都通过。
3. 提交信息用 Conventional Commits，例如 `feat(extractor): add bilibili adapter`。
4. 涉及行为变化的改动要同步更新文档。
5. PR 描述写清改了什么、为什么、怎么验证的。

## 最常见的贡献：新增平台适配器

这也是最有价值的贡献，因为平台页面结构变化很快。步骤见 [DEVELOPMENT.md](DEVELOPMENT.md) 的"新增一个平台适配器"。

两条硬要求：

- 必须附带 `tests/fixtures/` 下的离线 HTML 夹具与单元测试。测试不允许请求真实站点，否则站点一变 CI 就红，且对目标站点不友好。
- 字段缺失就留空，不要用猜测值填充。下游宁可少一个字段，也不要错的数据。

## 报告 Bug

请附上：Clipo 版本、部署方式（Docker 或源码）、数据库类型、复现步骤、相关日志。

日志里的 API Key、Cookie、Token 已做脱敏，但粘贴前请再自查一遍。涉及具体平台抓取失败时，附上目标页面的链接类型（不必是私密内容）有助于定位。

## 安全问题

不要在公开 Issue 里报告安全漏洞。请通过私有渠道联系维护者，留出修复时间后再公开。

## 行为准则

就事论事，尊重他人时间。技术分歧常见，把理由讲清楚比坚持结论更有用。
