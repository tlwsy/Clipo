# iOS Shortcut 配置

配置说明统一维护在 [Shortcut 配置与验收](../shortcuts/README.md)。新版通用模板支持一次性配置码自动领取服务器地址与设备 Token；日常既可接收系统分享，也可在没有分享输入时读取剪贴板，适用于小红书和小黑盒的“复制链接”。

仓库提供 [clipo-save.unsigned.shortcut](../shortcuts/clipo-save.unsigned.shortcut) 未签名模板。服务端接口与模板请求契约已通过本地验证；Apple 签名、导入、配置文件、网页唤起和系统行为仍待苹果设备验收，M4 尚未全部通过。旧的固定地址/Token 版本不能直接使用新自动配置流程。详见 [构建进度](progress.md)。
