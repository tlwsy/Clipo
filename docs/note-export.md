# 单篇笔记多格式导出

Q4 第三阶段在已有资料库备份之外，增加单篇阅读稿。当前后端提供 Markdown 与独立 HTML 下载，前端导出菜单与 PDF 预览继续实施。导出不触发采集、模型调用或数据库写入，不需要新迁移，最新版本仍为 `0018_annotations`。

## 导出内容

- 标题、来源、作者（存在时）、发布时间（存在时）、保存时间、标签与原网页链接。
- 可选 AI 摘要及要点；未生成摘要时明确提示，仍保留完整原文。
- 按顺序输出正文标题、段落、富文本、图片、列表、引用、代码、表格、游戏卡片；折叠正文在导出时展开。旧版纯文字正文和保存时的选区保留。
- 可选有价值评论：只包含 `is_valuable=true` 的评论和回复，低分、未评分和未标记的评论不导出。被隐藏的父评论不会为提供上下文而重新加入；回复会标明性质。
- 可选私人高亮与批注：HTML 原文显示高亮及短悬浮提示，文末列出完整片段和批注；Markdown 文末使用编号、内容块和 UTF-16 偏移列出片段、颜色与批注，不依赖特定阅读器的彩色高亮扩展。重叠高亮采用较新的非空颜色，所有批注保留。
- 原文定位已失效的标注保留在文末并提示，不重新猜测或移动位置。关闭私人标注选项同时移除原文高亮、悬浮提示及文末列表。

## API

使用正常账号认证或本账号 API Token：

```text
GET /api/v1/notes/{note_id}/export/markdown
GET /api/v1/notes/{note_id}/export/html
```

两个端点均接受 `include_summary`、`include_comments`、`include_annotations`，默认全部为 `true`。例如只导出正文和元数据：

```text
GET /api/v1/notes/42/export/html?include_summary=false&include_comments=false&include_annotations=false
```

成功分别返回 UTF-8 `text/markdown` 和 `text/html`，带下载文件名（ASCII 后备名与 UTF-8 中文标题）、`Cache-Control: no-store, private`、`nosniff` 和限制脚本的 CSP。错误保持标准 JSON 契约；未登录返回 401，笔记不存在、已删除或属于其他账号返回 404。私人标注也独立按账号过滤。

## 格式与隐私边界

- HTML 包含样式，无需 Clipo 或 Node.js 服务即可打开。正文作为结构化文本转义，模型摘要禁用原始 HTML，不执行原网页快照、脚本、表单、iframe 或危险协议链接。
- 图片只保留公开 HTTP(S) 引用，不打包图片文件，也不在后端访问图片网站。HTML/PDF 预览加载图片时可能访问原网站；离线、防盗链或网络故障会导致图片缺失。模型摘要里的图片以链接显示。
- 导出包含私人标注时，文件也包含私人批注；发送给他人前应关闭该选项或核对预览。文件生成后不会因 Clipo 中删除笔记或撤销公开分享而失效。
- 此功能不是可恢复备份格式；恢复整个资料库仍使用设置中的 JSON/Markdown ZIP 备份。

## 实现入口与验证

- 后端：`services/note_export.py`、`schemas/note_export.py`、`api/v1/exports.py`。
- 模板：`backend/app/templates/exports/`，包括 Markdown、HTML 与独立打印样式。
- 定向测试：`.venv/bin/pytest backend/tests/unit/test_export_rendering.py backend/tests/integration/test_note_exports.py`；可向集成测试传入 `--postgres-url` 在隔离 schema 验证 PostgreSQL。
- 本次节点结果见 [构建进度](progress.md)。前端与浏览器 PDF 验收完成前不标记第三阶段结束。
