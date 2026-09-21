# 平台协议依据与验收边界

本文件记录适配器使用的公开协议参考。离线夹具只验证解析与安全边界；真实平台兼容性必须单独验收。

## 小红书

- 帖子先读取 HTML 的 `window.__INITIAL_STATE__`，支持 `xhslink.com`、`xhslink.cn` 及其 `www` 短链接，Cookie 不发送到短链接主机。
- 顶层评论接口：`GET https://edith.xiaohongshu.com/api/sns/web/v2/comment/page`；参数为 `note_id`、`cursor`、`top_comment_id`、`image_formats` 与 `xsec_token`。响应读取 `data.comments`、`data.cursor`、`data.has_more`。
- 登录探测协议：`GET /api/sns/web/v1/user/selfinfo`，只接受明确的 `data.result.success` 布尔值；公开内容能读取不视为登录已验证。设置页探测由持久化后台任务执行，结果按账号和凭据版本隔离。
- 协议结构参考 [MediaCrawler 客户端](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/client.py)，仅核对接口与字段，未复制其实现。请求签名使用 MIT 许可的 [xhshow 0.2.0](https://pypi.org/project/xhshow/0.2.0/)；签名库不负责发送网络请求。
- 网络请求仍由 Clipo 执行：固定官方 HTTPS API 主机、全部 DNS 校验、连接固定 IP、禁止 API 跳转、限制 MIME/5 MB/60 秒。每次采集选择一个 User-Agent，连续请求间隔 1–1.5 秒；分页另限 10 页、180 秒检查预算和用户评论上限，单个在途请求受上述超时限制。
- 缺少完整 Cookie 或 `xsec_token` 时保存页面已有评论并提示；分页接口明确报错时任务按现有重试/失败语义处理。游标重复、缺失或达到分页预算时保留已有评论并提示未完成。登录、风控和结构变化不会回显平台返回体或凭据。
- 分页接入前的旧提取缓存失效，之后降低采集上限仍可复用缓存副本。HTML 快照保持完整，评论页 JSON 不落盘；测试用的分页 JSON 为人工构造的虚构样本。

2026-09-21：使用用户提供的 `xhslink.cn` 样本进行无 Cookie 请求，已确认短链接跳转到官方登录页。这验证了链接类型和登录失败路径，尚不能证明已登录帖子采集和签名分页可用。

## 小黑盒

- 支持官网 `/app/bbs/link/{id}` 与 `api.xiaoheihe.cn/v3/bbs/app/api/web/share?link_id=…` 分享入口；不执行页面脚本。分享 ID 可能是与数字帖子 ID 不同的不透明字符串，通过响应 `link.share_url` 回指核对目标。
- 内容与顶层评论：`GET https://api.xiaoheihe.cn/bbs/app/link/tree`，读取 `result.link`、`result.comments[].comment[0]` 和 `has_more_floors`；分页使用 `link_id/is_first/page/index/limit/owner_only`。支持 JSON 文本块、HTML 文本与图片块，过滤脚本；保存原始 HTML 应用外壳。图片只保留链接。
- 依据：2026-09-21 官方网站公开脚本 `index-BMNbT8g-.js` / `index-CswQPfZy.js`。hkey 算法依据 MIT 许可 ParseHub，来源、版本和完整许可见根目录 `THIRD_PARTY_NOTICES.md`；固定输入向量与参考实现对照。没有使用第三方设备指纹服务。
- 登录客户端查询 `/account/restore_login`，成功需要明确的账号 ID 和 pkey，公开帖子可访问不代表 Cookie 有效；设置页已提供后台检测入口。返回的登录材料不保存、不输出。
- 复用全部 DNS 校验、IP 固定、API 禁止跳转与 JSON 类型/体积/超时限制。Cookie 仅发送官方 HTTPS 主机；每次采集固定随机 UA，请求间隔 1–1.5 秒，评论最多 10 页、180 秒检查预算和用户配置上限（0–100）。登录失效、设备验证、频控与结构变化分别提示，不回显上游报文。
- 接入前的通用页面缓存失效；新缓存按账号隔离，降低评论上限裁剪副本，提高到超过原上限重新抓取。

2026-09-21：用户提供的真实小黑盒分享链接在无 Cookie 的生产适配器请求中取得正文 1057 字符、42 个图片链接及 15 条评论，无分页警告；没有写入日常笔记。这仅验证此公开帖子的提取，不能代替登录有效性和真实模型评分验收。

随后以用户提供并加密保存的 Cookie 查询两平台身份接口，均返回明确登录有效；小黑盒认证采集仍取得同样的正文、图片和评论。小红书认证页面未通过现有 HTML 解析，需继续修复结构兼容；真实模型密钥未配置，未进行真实评分。

用户随后在设置页配置模型。小黑盒真实样本经临时队列/数据库完成摘要与评分落库：15 条评论中 12 条评分、1 条高价值，8 条摘要要点，无摘要或评分错误；此结果不等于人工评审评分质量。

小红书真实页面兼容修复：状态中的空 `new Map([])` / `new Set([])` 按限定字面形式解析为 JSON，不执行 JavaScript。用户样本实际完成 25 条评论、25 条评分、13 条高价值标记与摘要落库，无分页警告；验证使用临时数据库/队列，未修改日常笔记。真实页面缺失标题时保持空值。

## B 站

- 支持 `/video/BV…`、`/video/av…`、`p` 分 P 与 `b23.tv` 分享跳转。读取 `__INITIAL_STATE__.videoData`，缺失时查询官方 `GET /x/web-interface/view`；核对请求视频 ID，分 P 使用对应 cid，不替换成推荐视频或默认分 P。
- 公开字幕目录：`GET https://api.bilibili.com/x/player/wbi/v2?aid=…&cid=…`。从 `data.subtitle.subtitles` 选择中文优先、其次英文的一轨；字幕 JSON 仅读取 `body[].content`，来自 HTTPS 的 `aisubtitle.hdslb.com` 或 `i0/i1/i2.hdslb.com`，仍检查所有 DNS/IP、禁止跳转。标明语言后附于 `content.text`，因此原文和模型都能使用；单轨最多 200000 字符，截断会提示。需要登录或未返回字幕时仅保存简介并说明。
- 热评：`GET /x/v2/reply?oid=…&type=1&sort=2&pn=…&ps=20`，仅取顶层回复，不抓楼中楼；按 ID 去重、最多 5 页/180 秒检查预算，并服从 0–100 采集上限。字幕/热评读取失败时保留已取得内容并显示原因。元数据无法确认则任务失败。
- 不配置或使用 B 站 Cookie，不复用其他平台凭据，不下载视频或音频。接口与字段依据 [yt-dlp B 站适配器](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/bilibili.py) 的公开协议使用和 2026-09-21 官方接口响应核对；未复制其实现。
- 2026-09-21 对公开视频 `BV1xx411c7mD` 的实际请求取得标题、3 字符简介、1 个封面与 3 条评论；该样本没有公开字幕，已正确提示。离线夹具另验证字幕、分 P、跨页去重和拒绝非官方字幕主机。这个样本不能证明需要登录的字幕可用。

## YouTube

- 支持 watch、youtu.be、Shorts、live 和 embed 单视频链接，规范为同 ID 的 watch 页面。读取 `ytInitialPlayerResponse`、`ytInitialData` 及 JSON 形式的 `ytcfg.set`，不执行页面脚本；检查播放器 videoId 与请求一致，登录/年龄/地区/不可播放状态明确报错，不保存推荐内容。
- 字幕读取 `captions.playerCaptionsTracklistRenderer.captionTracks`，优先中文、其次英文的一轨；自动字幕保留标记。仅接受 HTTPS 的 `www.youtube.com` / `youtube.com` / `video.google.com` 官方 timedtext 路径，且 URL 的 v 必须与视频相同；请求 `fmt=json3` 后拼接 `events[].segs[].utf8`，标注语言后并入正文供模型使用，最多 200000 字符且截断提示。
- 只在评论区域寻找 continuation；通过 `POST https://www.youtube.com/youtubei/v1/next?prettyPrint=false` 请求评论数据。上下文只取页面给出的 WEB 版本和访客数据，固定官方 endpoint；不接收页面任意请求 URL，不使用登录 Cookie。先选择排序菜单首项（Top comments），随后解析 `commentThreadRenderer.comment.commentRenderer` 或 commentViewModel 引用的 `frameworkUpdates.entityBatchUpdate.mutations[].payload.commentEntityPayload`。
- 仅抓顶层评论，忽略楼中楼 continuation，按 ID 去重，最多 10 次接口调用、180 秒检查预算和 0–100 采集上限。点赞简写不是准确计数时留为默认 0。未知结构、频控、验证码或网络失败保留已取得内容并显示原因。
- 带 JSON 请求体的网络路径复用现有 IP 固定、全 DNS 校验、HTTPS 固定主机、禁止接口重定向、MIME/5 MB/超时限制；正文、访客数据和 continuation 不写日志。协议字段参考 [yt-dlp YouTube 适配器](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_video.py)，仅核对协议、未复制其实现。
- 2026-09-21：当前环境对 `www.youtube.com` 域名解析失败，未取得真实页面，也未完成线上字幕/评论验收。人工离线夹具验证语法解析、字幕入模、热评切换、跨页去重、两代评论结构及安全边界，不能替代线上兼容性。
