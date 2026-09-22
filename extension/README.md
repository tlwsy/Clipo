# Clipo 浏览器扩展

Chrome/Edge Manifest V3，无需单独编译。在浏览器扩展管理页开启开发者模式，“加载已解压的扩展程序”选择本目录。设置中填写 Clipo 地址和 API Token，允许访问该服务器后即可从 popup 或右键保存当前页面。

支持通用正文与选区、小红书/小黑盒可见 DOM 和顶层评论、快捷标签、分块上传与本机队列恢复。评论受页面加载状态和账号采集上限限制；真实站点与 Edge 验收状态见仓库 `docs/progress.md`。

源码仓库内运行 `make extension-package` 生成 `extension/out/clipo-extension-0.1.0.zip`。完整配置、权限说明、恢复和排障见仓库 `docs/extension.md`。
