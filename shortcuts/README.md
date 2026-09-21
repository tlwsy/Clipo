# iOS 分享到 Clipo

模板设计为：在 Safari 或其他 App 的分享面板运行“保存到 Clipo”，提取分享内容中的第一个链接，向自己的 Clipo 发出 POST。服务器接受后通知“已加入保存队列”，正文提取与 AI 摘要由后台继续完成，成功路径不打开浏览器。以下系统行为仍需苹果设备验收。

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

模板的错误分支读取 API 返回的 `error.message`，例如 Token 无效或 URL 不允许访问；iOS 是否将非 2xx 响应交给后续动作仍需实测。网络断开、TLS 错误或系统阻止请求时，“获取 URL 内容”可能直接终止快捷指令并显示系统错误，后续自定义通知/打开入口是否执行取决于 iOS，**这些失败路径尚未实机验证**；可手动打开 Clipo 查看是否已收到任务后再重试，避免重复保存。

首次授权之后，在分享面板点“保存到 Clipo”应完成提交；Apple 的首次授权不能由模板绕过。自托管站点不一定自动在 PWA 窗口打开，模板失败分支配置了 Clipo 网页入口，实际跳转仍待验收。

## 本地验证与实机待验收

2026-09-21，本地定向测试 **2 项通过**，按用户选择记录 iOS 实机待验收。测试使用临时数据库和测试签发的 API Token，读取模板中的 HTTP 方法、路径、请求头与 JSON 字段调用测试 API；不运行 Apple 快捷指令引擎，也不执行真实网页抓取或模型调用。

| 验证项 | 当前结果 |
| --- | --- |
| plist 解析及与生成器输出一致 | 本地通过 |
| 模板请求提交 | 本地返回 202 与任务 ID |
| 非法 URL / 已撤销 Token | 本地分别返回 422 / 401 和标准错误消息 |
| Mac 签名与 iOS 文件导入 | 待验收：签名成功，导入后动作完整、地址与 Token 问题可填写 |
| 分享入口与 URL 提取 | 待验收：Safari 网页、文本含链接、多个链接选第一条、无链接提示 |
| 首次授权与成功通知 | 待验收：网络/通知授权后再次分享无需打开浏览器，通知仅表示已入队 |
| API 错误分支 | 待验收：非法 URL、撤销 Token 后显示原因，继续时可打开队列入口 |
| 网络/TLS 错误 | 待验收：记录系统是否中断动作，以及自定义通知/入口是否可达 |

苹果设备验收时记录 macOS/iOS 版本、导入方式和各项结果；记录中不包含 Token。签名、导入和 iOS 一次点击保存尚未验证，**M4 尚未全部通过**；阶段验证记录见 [构建进度](../docs/progress.md)。

## 维护

```bash
.venv/bin/python scripts/generate_shortcut.py
.venv/bin/pytest backend/tests/integration/test_shortcut_capture.py
```

生成器使用固定 UUID，输出可审查的 XML plist。不要在生成器或仓库模板写入个人服务器凭据。
