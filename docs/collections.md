# 空间

Q4 计划第一阶段。空间为用户私有的扁平多对多组织方式，不自动创建默认空间；全部笔记始终包含未分配笔记。删除空间只删除归属，不删除笔记。

## 数据与 API

- `0017_collections` 新增 `collections`、`notes_collections`，兼容 SQLite 和 PostgreSQL。沿用现有整数用户/笔记 ID；空间也使用整数 ID，不照搬计划书的 UUID 示例。
- 名称去除首尾空白，1–100 字符，同账号唯一；8 种预设色，可选 folder、briefcase、book、heart、laptop、star 图标。
- `/api/v1/collections` 支持 GET / POST；`/{id}` 支持 PATCH / DELETE；`/{id}/notes` 支持 GET / POST / DELETE。成员写入使用 `{"note_ids": [1, 2]}`，每批 1–100 项，重复添加或移除幂等。
- `GET /collections?note_id=1` 查询单篇所属空间；`GET /notes?collection_id=1` 可组合既有搜索、标签、收藏和游标分页。
- 所有读取和写入限定当前用户。混入不存在或其他用户的笔记时整批失败。空间详情缺失/越权返回 404；列表过滤越权空间不返回笔记。
- 回滚到 `0016_comment_threads` 会移除空间及归属数据，保留笔记与原有数据。

## 当前边界

空间 API 已实现；页面正在接入。空间暂不接入 PWA 离线写队列；现有 JSON/Markdown 资料库备份尚不包含空间与归属，备份笔记能力不受影响。
