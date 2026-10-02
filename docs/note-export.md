# 单篇笔记多格式导出

Q4 第三阶段在已有资料库备份之外，增加 Markdown、HTML 与 PDF 单篇阅读稿。导出不触发采集、模型调用或数据库写入，不需要新迁移，最新版本仍为 `0018_annotations`。

## 网页操作

1. 打开笔记详情，点击右上方“导出笔记”。
2. 选择是否包含 AI 摘要、有价值评论和私人标注；默认全部包含。
3. 选择“导出为 Markdown”或“导出为 HTML”，在浏览器下载列表中查看文件。
4. 选择“导出为 PDF”打开预览，可继续修改选项；待预览准备好后点击“打印 / 保存为 PDF”，在浏览器打印窗口选择“另存为 PDF”。取消打印不会生成文件，页面不会把打印调用报告为保存成功。

导出需要联网，通过现有认证客户端处理续期；失败后可重试，关闭弹窗会取消未完成的请求，不加入离线写队列。文件名包含清理后的标题与笔记 ID。预览图片等待最多 8 秒，超时停止图片加载并提示，可用“重新加载预览”重试。

## 导出内容

- 标题、来源、作者（存在时）、发布时间（存在时）、保存时间、标签与原网页链接；导出时间统一标示 UTC。
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
- 打印稿采用白底 A4、分页边距、标题防孤行、表格/图片分页约束和高亮颜色。支持 CSS 页边距框的浏览器显示 Clipo 页眉及“当前页 / 总页数”；建议关闭浏览器自带页眉页脚以免重复。最终分页、字体和系统打印目的地受浏览器与设备影响，Safari、Edge 和移动端系统打印尚待实机验证。
- PDF 预览使用无脚本沙箱 iframe；文件来自当前账号的下载接口，公开分享页面不提供该入口。HTML 使用固定阅读稿样式，不继承深色阅读偏好或本文自定义背景。

## 实现入口与验证

- 后端：`services/note_export.py`、`schemas/note_export.py`、`api/v1/exports.py`。
- 模板：`backend/app/templates/exports/`，包括 Markdown、HTML 与独立打印样式。
- 前端：`components/export-menu.tsx`、`components/pdf-export-dialog.tsx`、`lib/note-export.ts`；选项类型由 OpenAPI 生成。
- 定向测试：`.venv/bin/pytest backend/tests/unit/test_export_rendering.py backend/tests/integration/test_note_exports.py`；可向集成测试传入 `--postgres-url` 在隔离 schema 验证 PostgreSQL。
- 浏览器：先 `make build`，再执行 `uv run --no-project --with playwright python scripts/smoke_note_export.py`。脚本使用临时 API、真实 worker、离线模型与本地图片响应，验证下载、续期、选项、重试、打印事件、独立 HTML、实际 PDF 渲染及 390px 布局，产物保存在忽略提交的 `frontend/test-results/`。
- 本次节点结果及本机测试 Compose 验收见 [构建进度](progress.md)，本地通过不代表远端 CI、其他浏览器或移动端系统打印已验收。
