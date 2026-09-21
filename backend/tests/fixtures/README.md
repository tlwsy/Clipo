# 离线 HTML 夹具

`xiaohongshu.html` 是人工构造的最小回归夹具，描述本节点支持的
`window.__INITIAL_STATE__.note.noteDetailMap[帖子 ID]` 结构，包含正文、图片、作者、
毫秒时间戳及页面内嵌评论（驼峰与下划线字段）。账号、评论和链接均为虚构。
`xiaohongshu-login.html` 与 `xiaohongshu-changed.html` 分别模拟登录页和未知结构。

这些夹具不来自真实账号，不证明当前线上页面仍采用相同结构。平台实机验收需要另行进行；
发现结构变更时应添加经脱敏的最小夹具并更新适配器。测试不得访问真实站点。
