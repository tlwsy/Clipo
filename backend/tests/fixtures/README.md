# 离线 HTML 夹具

`xiaohongshu.html` 是人工构造的最小回归夹具，描述本节点支持的
`window.__INITIAL_STATE__.note.noteDetailMap[帖子 ID]` 结构，包含正文、图片、作者、
毫秒时间戳及页面内嵌评论（驼峰与下划线字段）。账号、评论和链接均为虚构。
`xiaohongshu-login.html` 与 `xiaohongshu-changed.html` 分别模拟登录页和未知结构。
`xiaohongshu-comment-limit.html` 补充空评论、重复编号和不同点赞顺序的样本，验证
采集上限只计算有效的唯一评论、保留页面顺序，以及关闭评论采集时正文仍完整。
`xiaohongshu-comments-page1.json` / `page2.json` 是虚构的签名评论接口响应，覆盖跨页重复、
追加评论与终页；接口字段依据见 `docs/platform-protocols.md`。测试实际生成签名，但网络使用 MockTransport。

这些夹具不来自真实账号，不证明当前线上页面仍采用相同结构。平台实机验收需要另行进行；
发现结构变更时应添加经脱敏的最小夹具并更新适配器。测试不得访问真实站点。

`xiaoheihe.html` 是最小应用外壳；`xiaoheihe-page1.json` / `page2.json` 是人工构造的
官方接口响应，含文本/HTML/图片块、作者、时间、顶层评论与跨页重复，最终得到 12 条评论。
所有账号、帖子和图片链接均为虚构；小黑盒签名测试采用固定时间与 nonce。

`xiaohongshu-collections.html` 模拟真实页面发现的空 Map/Set 状态序列化语法，
其余帖子文字和数据均为虚构。验证有限字面量解析及字符串保留，不执行任何页面脚本。

`bilibili.html`、`bilibili-player.json`、`bilibili-captions.json` 与
`bilibili-comments1.json` / `comments2.json` 均为人工构造的回归数据，
覆盖分 P、语言选择、字幕文本和两页 23 条唯一顶层热评。未包含真实视频正文、作者或评论。

`youtube.html` 与 `youtube-captions.json` 模拟播放器/页面配置/英文自动字幕；
`youtube-comments-initial.json` / `top.json` / `page2.json` 覆盖切换热评、旧评论 renderer、
新版实体引用、跨页重复和不得采集的楼中楼。所有视频、作者、评论和访客标识均为虚构。
