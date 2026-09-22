// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";

import Link from "next/link";
import { AppShell } from "@/components/app-shell";

export default function ShortcutGuidePage() {
  return (
    <AppShell>
      <div className="page-heading">
        <div>
          <span className="eyebrow">SAVE FROM YOUR IPHONE</span>
          <h1>iPhone 快捷指令</h1>
          <p>先连接一次，以后复制链接就能保存。</p>
        </div>
      </div>
      <section className="settings-card shortcut-guide">
        <h2>开始使用</h2>
        <ol>
          <li>
            安装支持自动配置的“保存到 Clipo”。旧的固定地址、手填 Token
            版本需要替换。
          </li>
          <li>
            在这台 iPhone 上打开 Clipo 设置，找到“iPhone
            快捷指令”，点击“生成设备配置”。
          </li>
          <li>
            点击“打开快捷指令并配置”，核对服务器地址，允许网络和文件访问。看到“配置已保存”后即可使用。
          </li>
          <li>
            在小红书或小黑盒复制帖子链接，再运行快捷指令；Safari
            也可从系统分享菜单运行。
          </li>
        </ol>
        <Link className="button" href="/settings/#shortcut">
          前往配置此设备
        </Link>
        <p>
          配置 5
          分钟内有效，只能领取一次。网页显示“已领取”后，还需快捷指令成功保存文件；如果系统中途报错，请重新生成配置，并在设置的
          API Token 列表撤销未使用的令牌。
        </p>
        <h2>安装与自定义</h2>
        <p>
          前往设置页，点击“安装快捷指令”，即可通过 iCloud
          添加已验证的通用版，再为这台设备生成配置。如果服务器未提供安装链接，或需要自行修改，可使用下面的未签名模板和制作步骤。未签名文件需在
          Mac 签名后导入，也可在 iPhone 手动搭建。
        </p>
        <a className="button secondary" href="/api/v1/shortcuts/template">
          下载未签名模板（供 Mac 签名）
        </a>
        <details>
          <summary>在 Mac 签名</summary>
          <p>
            把下载的模板放入当前文件夹，在“终端”执行，再将签名文件传到 iPhone
            导入：
          </p>
          <pre>
            <code>
              {
                "shortcuts sign --mode anyone --input clipo-save.unsigned.shortcut --output clipo-save.shortcut"
              }
            </code>
          </pre>
          <p>
            保持指令名称为“保存到 Clipo”（中间有空格）。模板不需要填写个人
            Token。
          </p>
        </details>
        <details>
          <summary>在 iPhone 手动搭建新版（只需制作一次）</summary>
          <p>
            在“快捷指令”App 创建“保存到 Clipo”，开启“在共享表单中显示”，接受
            URL、Safari 网页和文本。动作名称可能随 iOS 版本略有不同。
          </p>
          <ol>
            <li>
              添加“如果”：如果“快捷指令输入”有值，设变量“Clipo
              输入”为它；否则添加“获取剪贴板”，设同一变量为剪贴板。结束“如果”。
            </li>
            <li>
              获取“Clipo 输入”的文本，再用“匹配文本”匹配{" "}
              <code>^clipo-setup:</code>
              。如果匹配结果有值，执行接下来的配置分支。
            </li>
            <li>
              用“替换文本”删除开头的 <code>^clipo-setup:</code>
              ，开启正则表达式。将结果“从输入中获取字典”，分别取{" "}
              <code>server_url</code> 和 <code>code</code>。
            </li>
            <li>
              显示带取消按钮的提醒，展示服务器地址。随后“获取 URL 内容”：地址为{" "}
              <code>server_url</code> 加{" "}
              <code>/api/v1/shortcuts/pairings/consume</code>，方法
              POST，请求体选 JSON，文本字段 <code>code</code> 取刚得到的值。
            </li>
            <li>
              如果返回字典的 <code>token</code>{" "}
              有值，将整个返回字典转换为文本，存储到 iCloud Drive 的 Shortcuts
              文件夹，文件名 <code>Clipo.json</code>
              ，关闭“询问存储位置”、开启覆盖。显示“Clipo
              配置已保存”。否则显示返回字典的 <code>error.message</code>
              。停止此快捷指令，结束配置分支。
            </li>
            <li>
              普通保存分支：从“Clipo 输入”获取
              URL；没有链接时显示提示并停止，有链接时取第一项。
            </li>
            <li>
              读取同一 Shortcuts 文件夹的 <code>Clipo.json</code>，转成字典，取{" "}
              <code>server_url</code> 和 <code>token</code>
              。文件不存在时提示先配置并停止。
            </li>
            <li>
              “获取 URL 内容”：地址为 <code>server_url</code> 加{" "}
              <code>/api/v1/captures</code>，方法 POST，请求头{" "}
              <code>X-Clipo-Token</code> 为 <code>token</code>；请求体
              JSON，文本字段 <code>url</code> 为第 6 步的第一个链接。
            </li>
            <li>
              返回字典中有 <code>job_id</code> 就通知“已加入保存队列”；否则显示{" "}
              <code>error.message</code>。网络错误可能由系统直接提示。
            </li>
          </ol>
        </details>
        <h2>让复制链接更方便</h2>
        <p>
          把快捷指令加到主屏幕，或在 iPhone“设置 → 辅助功能 → 触控 →
          轻点背面”绑定它。以后在帖子里复制链接，再点图标或轻点背面即可保存。首次运行可能询问是否允许粘贴、网络、文件和通知。
        </p>
        <p>
          配置保存在 iCloud Drive 的 <code>Shortcuts/Clipo.json</code>，可能随
          iCloud 同步。分享通用快捷指令时不要附带这个文件，也不要把 Token
          写进指令动作。重新配置会替换此文件，但旧 Token 仍需在 Clipo
          设置中单独撤销。
        </p>
        <p>
          入队成功后，正文提取和 AI
          摘要继续在服务端处理；到保存队列查看结果。离开电脑热点后，当前局域网地址将无法访问。
        </p>
        <div className="notice">
          服务器配置和本地请求契约已验证。苹果设备上的导入、文件保存、剪贴板、唤起和通知仍需实机测试。
        </div>
      </section>
    </AppShell>
  );
}
