# 空间

Q4 计划第一阶段。空间为用户私有的扁平多对多组织方式，不自动创建默认空间；全部笔记始终包含未分配笔记。删除空间只删除归属，不删除笔记。

## 数据与 API

- `0017_collections` 新增 `collections`、`notes_collections`，兼容 SQLite 和 PostgreSQL。沿用现有整数用户/笔记 ID；空间也使用整数 ID，不照搬计划书的 UUID 示例。
- 名称去除首尾空白，1–100 字符，同账号唯一；8 种预设色，可选 folder、briefcase、book、heart、laptop、star 图标。
- `/api/v1/collections` 支持 GET / POST；`/{id}` 支持 PATCH / DELETE；`/{id}/notes` 支持 GET / POST / DELETE。成员写入使用 `{"note_ids": [1, 2]}`，每批 1–100 项，重复添加或移除幂等。
- `GET /collections?note_id=1` 查询单篇所属空间；`GET /notes?collection_id=1` 可组合既有搜索、标签、收藏和游标分页。
- 所有读取和写入限定当前用户。混入不存在或其他用户的笔记时整批失败。空间详情缺失/越权返回 404；列表过滤越权空间不返回笔记。
- 回滚到 `0016_comment_threads` 会移除空间及归属数据，保留笔记与原有数据。

## 使用方式

1. 主导航进入“空间”，创建空间并选择名称、颜色及可选图标；空间卡片提供编辑/删除按钮，支持触摸与键盘操作。
2. “全部笔记”点击“多选笔记”，勾选后选择“添加到空间”；每批最多 100 篇，跨分页保留选择，切换搜索/标签/收藏条件清空选择。批量添加保持其他归属。
3. 空间详情可“添加笔记”，在可分页/搜索的列表中选择笔记，也可逐篇“从空间移除”。
4. 笔记详情点击“管理所属空间”；已有归属预勾选，取消勾选可移出，支持搜索空间和快速创建。
5. 静态页面地址为 `/collections/` 和 `/collections/?id=1`，无需生产 Node.js 服务。对话框支持 Escape 关闭和焦点约束；请求提交中避免重复操作。

## 当前边界

空间管理需要联网，暂不接入 PWA 离线缓存和写队列；网络错误会明确显示，可关闭/重试。跨多个空间提交分别执行，部分失败保留已成功结果并提示重试。JSON 资料库备份包含空间（含空空间）、颜色/图标、创建/修改时间及笔记归属/加入时间；Markdown 标示所属空间。恢复会重新映射笔记 ID，同名空间合并归属且保留目标空间样式，原笔记不被覆盖。旧备份仍可导入；包含空间的新备份需导入支持空间的版本。

## 验证

- API 与仓储测试：`.venv/bin/pytest backend/tests/integration/test_collections.py`；可加 `--postgres-url` 在临时隔离 schema 验证 PostgreSQL。
- 组件/API 客户端测试：`npm --prefix frontend test -- lib/collections.test.tsx`。
- 构建后执行 `uv run --no-project --with playwright python scripts/smoke_collections.py`，覆盖 CRUD、批量添加、分页、多空间、单篇预勾选、快速创建、失败状态和手机布局。若本机配置 HTTP 代理，验收进程需让 `127.0.0.1,localhost` 直连。
