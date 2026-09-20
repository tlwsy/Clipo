# 浏览器扩展

扩展是桌面端的录入入口，也是小红书、小黑盒这类需要登录态站点最可靠的抓取方式：它运行在你已登录的浏览器里，直接读取页面 DOM，不需要在服务端保存 Cookie，也不触发反爬。

支持 Chrome 与 Edge 等 Chromium 浏览器（Manifest V3）。Firefox 适配排在 MVP 之后。

## 安装

1. 从 Releases 下载 `clipo-extension-<version>.zip` 并解压。
2. 打开 `chrome://extensions`，右上角开启开发者模式。
3. 点"加载已解压的扩展程序"，选择解压出的目录。
4. 点扩展图标 → 设置，填入服务器地址与 API Token，点"测试连接"。

API Token 的获取：在 Clipo 网页端 设置 → API Token → 新建，命名为 `chrome-extension`。明文只显示一次，复制后立即粘贴到扩展设置里。Token 可随时撤销，撤销后该扩展立刻失效，不影响其他客户端。

## 使用

三种触发方式，行为一致：

- 页面右键 → 保存到 Clipo
- 点击工具栏图标 → 保存当前页
- 先选中一段文字再右键，选区会作为附加备注一起提交

保存后 popup 显示结果。默认全自动，不要求你确认任何内容；如果想顺手加标签，popup 里有快捷标签输入框，跳过也无妨。

## 权限说明

只申请四项：

| 权限 | 用途 |
|------|------|
| `activeTab` | 仅在你主动触发时读取当前标签页 |
| `scripting` | 注入内容脚本以提取结构化内容 |
| `storage` | 保存服务器地址与 Token |
| `contextMenus` | 右键菜单项 |

不申请 `<all_urls>`，因此安装时不会出现"读取你在所有网站上的数据"这类提示。扩展不在后台监听浏览记录，不主动上传任何页面。

## 架构

```
extension/
├── manifest.json
├── background/          service worker：接收指令、调用 API、结果通知
├── content/             按平台注入的内容脚本
│   ├── base.ts          共享的 payload 结构与工具
│   ├── xiaohongshu.ts
│   ├── xiaoheihe.ts
│   └── generic.ts       通用页面：标题、正文、选区
├── popup/               保存状态与快捷标签
└── options/             服务器地址、Token、连通性测试
```

内容脚本产出的 payload 与后端 Extractor 的 `CapturedContent` 字段一致，后端收到 payload 后直接进入规范化步骤，跳过网络抓取。这套字段定义是两侧的契约，改动要同步。

提交的 payload 形如：

```json
{
  "url": "https://www.xiaohongshu.com/explore/xxxx",
  "source_hint": "xiaohongshu",
  "selection": "可选的选中文本",
  "payload": {
    "title": "帖子标题",
    "author": { "name": "作者", "url": "https://..." },
    "published_at": "2026-09-01T10:00:00Z",
    "text": "正文……",
    "images": ["https://..."],
    "comments": [{ "author": "甲", "content": "……", "likes": 128, "replies": 3 }]
  }
}
```

大 payload：超过 5 MB 时先请求建立任务拿到 `job_id`，再分块上传内容。多数页面远低于这个量级，走一次性提交即可。

## 新增平台适配

1. 在 `content/` 新建与后端适配器同名的文件，实现 `matches(url)` 与 `extract(document)`。
2. 在 `manifest.json` 的内容脚本匹配规则中登记域名。
3. 字段对齐 `base.ts` 的类型定义；缺失字段留空而不是编造。
4. 后端同步补一个服务端适配器作为移动端兜底（见开发指南）。

评论抓取注意懒加载：先滚动或点击"查看更多"展开到上限条数，再统一读取，否则只能拿到首屏几条。

## 排障

| 现象 | 处理 |
|------|------|
| 测试连接失败 | 核对地址含协议与端口；HTTPS 证书自签时浏览器需先信任 |
| 401 未认证 | Token 被撤销或复制不全，重新生成 |
| 保存成功但评论很少 | 页面评论未展开，或该平台适配器需要更新 |
| 图标点击无反应 | 查看 `chrome://extensions` 中该扩展的 service worker 日志 |
| 更新扩展后设置丢失 | 开发者模式下重新加载会保留 storage，删除后重装则不会 |
