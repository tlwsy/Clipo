# iOS Shortcut 配置

配置说明统一维护在 [Shortcut 配置与验收](../shortcuts/README.md)。新版通用模板支持一次性配置码自动领取服务器地址与设备 Token；日常既可接收系统分享，也可在没有分享输入时读取剪贴板，适用于小红书和小黑盒的“复制链接”。

通过 [iCloud 安装“保存到 Clipo”](https://www.icloud.com/shortcuts/0cfcf8c51dcc4c2f9bc6d621e5d2dd09)，或点击设置页的“安装快捷指令”。用户已于 2026-09-22 确认此分享版本完成 iOS 实机核验；新部署配置示例已包含安装链接，已有部署按上方指南填写 `CLIPO_SHORTCUT_INSTALL_URL` 并重启服务。

仓库另提供 [clipo-save.unsigned.shortcut](../shortcuts/clipo-save.unsigned.shortcut) 未签名模板，仅通过本地生成与请求契约验证；其 Mac 签名及导入未另行验收。旧的固定地址/Token 版本不能直接使用新自动配置流程。详见 [构建进度](progress.md)。
