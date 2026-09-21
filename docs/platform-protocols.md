# 平台协议依据与验收边界

本文件记录适配器使用的公开协议参考。离线夹具只验证解析与安全边界；真实平台兼容性必须单独验收。

## 小红书

- 帖子先读取 HTML 的 `window.__INITIAL_STATE__`，支持 `xhslink.com`、`xhslink.cn` 及其 `www` 短链接，Cookie 不发送到短链接主机。
- 顶层评论接口：`GET https://edith.xiaohongshu.com/api/sns/web/v2/comment/page`；参数为 `note_id`、`cursor`、`top_comment_id`、`image_formats` 与 `xsec_token`。响应读取 `data.comments`、`data.cursor`、`data.has_more`。
- 登录探测协议：`GET /api/sns/web/v1/user/selfinfo`，只接受明确的 `data.result.success` 布尔值；公开内容能读取不视为登录已验证。当前只有内部客户端方法，设置页探测入口另行接入。
- 协议结构参考 [MediaCrawler 客户端](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/client.py)，仅核对接口与字段，未复制其实现。请求签名使用 MIT 许可的 [xhshow 0.2.0](https://pypi.org/project/xhshow/0.2.0/)；签名库不负责发送网络请求。
- 网络请求仍由 Clipo 执行：固定官方 HTTPS API 主机、全部 DNS 校验、连接固定 IP、禁止 API 跳转、限制 MIME/5 MB/60 秒。每次采集选择一个 User-Agent，连续请求间隔 1–1.5 秒；分页另限 10 页、180 秒检查预算和用户评论上限，单个在途请求受上述超时限制。
- 缺少完整 Cookie 或 `xsec_token` 时保存页面已有评论并提示；分页接口明确报错时任务按现有重试/失败语义处理。游标重复、缺失或达到分页预算时保留已有评论并提示未完成。登录、风控和结构变化不会回显平台返回体或凭据。
- 分页接入前的旧提取缓存失效，之后降低采集上限仍可复用缓存副本。HTML 快照保持完整，评论页 JSON 不落盘；测试用的分页 JSON 为人工构造的虚构样本。

2026-09-21：使用用户提供的 `xhslink.cn` 样本进行无 Cookie 请求，已确认短链接跳转到官方登录页。这验证了链接类型和登录失败路径，尚不能证明已登录帖子采集和签名分页可用。
