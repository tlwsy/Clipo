# iOS Shortcut 配置

iOS 分享入口使用“快捷指令”接收链接，通过 API Token 提交到 Clipo 的后台保存队列。配置说明统一维护在 [Shortcut 配置与验收](../shortcuts/README.md)，包含 Mac 签名命令、iPhone 手动创建步骤和错误处理说明。

仓库提供的是 [clipo-save.unsigned.shortcut](../shortcuts/clipo-save.unsigned.shortcut) **未签名模板**，不是已通过 iOS 验收的安装包。本地已验证模板可解析、生成结果一致，以及请求字段能够通过 API Token 完成提交、非法 URL 和 Token 撤销验证；尚未运行 Apple 快捷指令引擎。

按本阶段选择，先完成本地验证并记录实机待验收。Apple 签名、iOS 导入、系统分享入口、首次授权、通知及错误分支仍需 Mac/iPhone 验证，M4 尚未全部通过。详细记录见 [构建进度](progress.md)。
