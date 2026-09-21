# iOS 分享到 Clipo

在 Safari 或其他 App 的分享面板运行“保存到 Clipo”，提取分享内容中的第一个链接，向自己的 Clipo 发出 POST。服务器接受后通知“已加入保存队列”，正文提取与 AI 摘要由后台继续完成，成功路径不打开浏览器。

本目录的 [clipo-save.unsigned.shortcut](clipo-save.unsigned.shortcut) 是**未签名模板**，尚未在 iPhone 上导入或运行验收。当前开发环境是 Linux，没有 Apple 的签名工具；不能将这个文件当成已经可直接安装的 iOS 成品。现代 iOS 的文件导入需要先在 Mac 签名，或按后面的步骤直接在 iPhone 创建。

## 准备

1. iPhone 能通过 HTTPS 访问你的 Clipo。服务器地址使用实际域名，例如 `https://clipo.example.com`，末尾不加 `/`，不要使用手机自己的 `localhost`。
2. 登录 Clipo → 设置 → API Token，创建名为“iPhone Shortcut”的独立 Token；只显示一次，在自己的设备保存。
3. 不要分享已填入 Token 的快捷指令。停用时在 Clipo 设置撤销该 Token。

## Mac 签名与导入

仓库模板只包含示例地址和占位 Token，**签名与分发前不要填入真实凭据**。在支持“快捷指令”的 macOS 上执行：

```bash
shortcuts sign --mode anyone \
  --input shortcuts/clipo-save.unsigned.shortcut \
  --output /tmp/clipo-save.shortcut
```

通过 AirDrop 或“文件”把签名后的 `/tmp/clipo-save.shortcut` 传到 iPhone，再导入“快捷指令”。在导入问题或编辑器前两处“文本”动作中填入自己的服务器地址与 API Token。首次运行可能要求允许网络访问和通知，确认目标是自己的服务器。

Apple 的签名说明见 [Sign shortcuts](https://support.apple.com/guide/shortcuts-mac/sign-shortcuts-apdf01f8c054/mac)。签名文件不纳入 Git；不同系统版本的导入提示和动作字段须在苹果设备复验。

## 无 Mac 时手动创建

在 iPhone“快捷指令”中新建“保存到 Clipo”，详情中启用“在共享表单中显示”，接受 URL、Safari 网页和文本。依次添加：

1. “文本”：填写服务器地址，设变量“Clipo 服务器”。再用一个“文本”填写 API Token，设变量“Clipo Token”。
2. “从输入中获取 URL”：输入为“快捷指令输入”；“从列表中获取项目”：第一项。无 URL 时显示通知“Clipo 未收到链接”并停止。
3. “URL”：组合“Clipo 服务器”与 `/api/v1/captures`。
4. “获取 URL 内容”：方法 **POST**；请求头 `X-Clipo-Token` 为“Clipo Token”；请求体 **JSON**，添加文本字段 `url`，值为上面提取的 URL。
5. “获取字典值”：读取返回体的 `job_id`；如果有值，“显示通知”：`已加入保存队列，正文和摘要将在后台处理。`。
6. 否则从返回字典取 `error`，再取 `message`，显示失败通知和提醒；提醒提供取消按钮，继续时“打开 URL”：服务器地址加 `/jobs/`。该页面可查看任务，Token 无效时先登录并前往设置重新配置。

正常保存只调用 API，不添加“打开 URL”动作到成功分支。通知“已加入队列”表示服务器接收成功，不代表网页抓取或摘要已完成。每次运行视为一次新保存；不要连续点击多次。

## 失败与验收限制

API 返回的标准错误会取 `error.message`，例如 Token 无效或 URL 不允许访问。网络断开、TLS 错误或系统阻止请求时，“获取 URL 内容”可能直接终止快捷指令并显示系统错误，后续自定义通知/打开入口是否执行取决于 iOS，**这条失败路径尚未实机验证**；可手动打开 Clipo 查看是否已收到任务后再重试，避免重复保存。

首次授权之后，在分享面板点“保存到 Clipo”应完成提交；Apple 的首次授权不能由模板绕过。自托管站点不一定自动在 PWA 窗口打开，失败分支保证提供 Clipo 的网页入口。

本机仅验证了模板可解析、可复现生成，以及模板请求字段通过真实 API Token 完成提交、错误与撤销认证。以下仍待 Mac/iPhone 完成：签名成功、导入字段、系统分享入口、首次授权、通知、有效链接与错误分支。未把这些列为已通过。

## 维护

```bash
.venv/bin/python scripts/generate_shortcut.py
.venv/bin/pytest backend/tests/integration/test_shortcut_capture.py
```

生成器使用固定 UUID，输出可审查的 XML plist。不要在生成器或仓库模板写入个人服务器凭据。
