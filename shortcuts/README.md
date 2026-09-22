# iOS 分享与复制链接保存到 Clipo

通过 [iCloud 安装“保存到 Clipo”](https://www.icloud.com/shortcuts/0cfcf8c51dcc4c2f9bc6d621e5d2dd09)，再到 Clipo 设置页为设备生成配置。此版本由用户于 2026-09-22 确认完成 iOS 实机核验。

快捷指令接收 Clipo 生成的一次性配置输入，领取服务器地址和设备 Token，保存为 iCloud Drive 的 `Shortcuts/Clipo.json`。平常运行时，有分享输入就使用分享内容，没有输入就读取剪贴板，提取第一个链接提交后台。适用于小红书、小黑盒只有“复制链接”的情况。本目录另提供自动配置协议 v1 的 [未签名通用模板](clipo-save.unsigned.shortcut)，供自行制作与修改。

模板中没有个人地址和凭据；配置文件在首次运行时生成，可能随 iCloud 同步。不要分享配置文件，也不要把真实 Token 填回公共模板。旧的固定地址/Token 两动作版不支持自动配置，须替换为新版。

## 当前可用范围

服务端已提供配置码签发、领取、状态查询、取消和设备 Token 撤销；本地契约测试覆盖请求字段与生成一致性。设置页已提供“iPhone 快捷指令”区域，支持安装、生成配置、唤起、复制配置文本、取消和领取状态。内置使用指南位于 `/shortcuts/`。用户实机核验针对上方 iCloud 分享版本；仓库生成的未签名模板仍仅通过本地契约验证，未另行完成 Mac 签名与导入验收。

新部署的 `.env.example` 已填写该链接。已有部署需在 `.env` 设置以下值，再执行 `docker compose up -d app`（源码部署重启 API），设置页会显示“安装快捷指令”：

```dotenv
CLIPO_SHORTCUT_INSTALL_URL=https://www.icloud.com/shortcuts/0cfcf8c51dcc4c2f9bc6d621e5d2dd09
```

## 在网页配置此设备

1. 用 iPhone Safari 打开自己的 Clipo，登录后进入设置 → iPhone 快捷指令。页面显示当前连接的服务器，保留实际端口；正式使用应为 HTTPS。
2. 已发布通用版链接时，点击“安装快捷指令”；尚未发布时通过“安装与使用指南”取得模板或手动搭建说明，旧版不可用于自动配置。
3. 填写设备名称，点击“生成设备配置”，再点击“打开快捷指令并配置”。第二次点击保证 iOS 在用户操作中打开快捷指令；服务器没有把真实 Token 放入启动 URL。
4. 确认指令展示的服务器地址，允许访问网络和文件，等待“Clipo 配置已保存”。网页显示“已领取”只证明凭据已签发，仍需手机完成文件保存。
5. 如果没有自动打开，展开“没有自动打开？”，复制配置文本，再手动运行新版指令。HTTP 热点可能无法自动复制，此时长按文本复制。不要把这段有效配置转发给他人。

配置文本仅保存在当前页面内存，刷新后不恢复；5 分钟到期或生成新码会失效。“取消配置”只取消未领取的码。已领取设备会出现在 API Token 列表，可单独撤销；重新配置同一台手机不会自动撤销旧 Token。

若 iOS 提示找不到“保存到+Clipo”，请更新服务后刷新设置页并重新生成配置，手机上的指令名称保持“保存到 Clipo”。启动链接使用百分号编码，名称中的空格必须编码为 `%20`；表单编码的 `+` 会被快捷指令当作名称中的加号。

## 制作可安装的通用模板

在 Mac 仓库根目录执行：

```bash
shortcuts sign --mode anyone \
  --input shortcuts/clipo-save.unsigned.shortcut \
  --output /tmp/clipo-save.shortcut
```

把签名文件传到 iPhone 导入，保持名称为“保存到 Clipo”（包含空格），按下方协议验收配置与保存。随后从快捷指令 App 生成 iCloud 分享链接，管理员通过 `CLIPO_SHORTCUT_INSTALL_URL` 配置到自己的服务。签名文件不提交仓库。Apple 说明见 [Sign shortcuts](https://support.apple.com/guide/shortcuts-mac/sign-shortcuts-apdf01f8c054/mac)。

没有 Mac 时可按下面的动作流程在 iPhone 手动创建一次，再分享无凭据的通用模板；动作中文名称可能随 iOS 版本变化。

## 模板动作流程

1. 指令详情开启“在共享表单中显示”，接受 URL、Safari 网页和文本。
2. 如果“快捷指令输入”有值，将其设为“Clipo 输入”；否则“获取剪贴板”，将结果设为“Clipo 输入”。
3. 将输入转为文本，以“匹配文本”检查 `^clipo-setup:`。有匹配时进入配置分支；普通帖子内容不会读取配置 JSON。
4. 配置分支：“替换文本”以正则删除开头的 `^clipo-setup:`，再“从输入中获取字典”。读取 `server_url` 和 `code`，显示带取消按钮的服务器确认提醒。
5. “获取 URL 内容”：向 `server_url` 加 `/api/v1/shortcuts/pairings/consume` 发 **POST**；请求体选 **JSON**，文本字段 `code` 取上一步的值。不需要 Token 请求头。
6. 读取响应字典的 `token`。有值才把**整个响应字典转成文本**，用“存储文件”保存到 iCloud Drive 的 Shortcuts 文件夹，文件名 `Clipo.json`，关闭每次询问、允许覆盖。显示配置完成通知并“停止此快捷指令”。错误时显示 `error.message` 并停止，保留旧文件。
7. 普通保存分支：“从输入中获取 URL”，输入为“Clipo 输入”。没有 URL 则通知“请先复制帖子链接”并停止；否则“从列表中获取项目”选第一项。
8. “获取文件”读取同一 Shortcuts 文件夹的 `Clipo.json`，关闭文件选择器。不存在时提示在 Clipo 配置设备并停止；存在则“从输入中获取字典”，读取 `server_url` 与 `token`。
9. “获取 URL 内容”：URL 为 `server_url` 加 `/api/v1/captures`；方法 **POST**；请求头 `X-Clipo-Token` 为配置中的 `token`；请求体 **JSON**，文本字段 `url` 为第 7 步取得的链接。
10. 返回 `job_id` 时通知“已加入保存队列”；否则显示 `error.message`，继续时打开服务器地址加 `/jobs/`。成功分支不打开浏览器。

配置 JSON 协议由服务器提供，手机只保存，不需要用户手填 Token。配置码有效 5 分钟且只能领取一次；重新生成会使该账号旧码失效，但不会自动撤销已经签发的 Token。网络失败或未保存文件时，回到 Clipo 重新生成配置，并在 API Token 列表撤销不再使用的令牌。

## 日常使用

小红书或小黑盒 → 复制链接 → 运行“保存到 Clipo”。可以将指令加到主屏幕，或在 iPhone“设置 → 辅助功能 → 触控 → 轻点背面”绑定它。复制内容包含标题和口令时，先提取 URL，再提交。首次粘贴、网络、通知或文件访问可能需要系统授权。

Safari 支持系统分享时直接选择该快捷指令。入队通知只表示服务器接收，抓取、平台 Cookie 和模型配置仍由 Clipo 后台处理。

## 验收边界

| 验证项 | 方式与边界 |
| --- | --- |
| 模板 plist 可解析、可复现生成 | 本地测试；不运行 Apple 引擎 |
| 一次性配置码、设备 Token、采集请求 | 本地临时库接口测试，覆盖过期、重复、撤销、账号隔离和事务 |
| 已发布 iCloud 版本的配置与保存流程 | 用户于 2026-09-22 确认完成 iOS 实机核验；非本地工具代验 |
| 仓库生成模板的 Mac 签名与导入 | 未另行验证；不等同于已发布的 iCloud 版本 |
| 无链接、API 错误等异常分支 | 未单独提供逐项实机结果；非 2xx 是否继续动作由系统决定 |
| 网络/TLS 错误 | 系统可能直接终止动作，自定义失败入口不保证执行 |

iOS 主流程已按用户确认记录验收；完整验证记录与其他平台边界见 [构建进度](../docs/progress.md)。

## 维护

```bash
.venv/bin/python scripts/generate_shortcut.py
.venv/bin/pytest backend/tests/integration/test_shortcut_capture.py backend/tests/integration/test_shortcut_pairing.py
```

生成器与公开模板下载接口共用 `backend/app/services/shortcut_template.py`。固定 UUID 保证输出可审查；下载接口不拼接用户凭据。
