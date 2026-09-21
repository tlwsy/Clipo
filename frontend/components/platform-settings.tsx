"use client";

import { useState, type FormEvent } from "react";

import { Icon } from "@/components/icon";
import { api, errorMessage, type Schema } from "@/lib/api";

const platforms = [
  {
    key: "xiaohongshu",
    name: "小红书",
    website: "https://www.xiaohongshu.com",
    requestHost: "edith.xiaohongshu.com",
    loginRequest: "selfinfo",
  },
  {
    key: "xiaoheihe",
    name: "小黑盒",
    website: "https://www.xiaoheihe.cn",
    requestHost: "api.xiaoheihe.cn",
    loginRequest: "restore_login",
  },
] as const;

export function PlatformSettings({
  initial,
}: {
  initial: Schema["PlatformCookiesResponse"];
}) {
  const [current, setCurrent] = useState(initial);
  const [cookies, setCookies] = useState({ xiaohongshu: "", xiaoheihe: "" });
  const [clear, setClear] = useState({ xiaohongshu: false, xiaoheihe: false });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const changed = platforms.some(({ key }) => clear[key] || cookies[key]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    const platform_cookies: Schema["PlatformCookiesUpdate"] = {};
    for (const { key } of platforms) {
      if (clear[key]) platform_cookies[key] = null;
      else if (cookies[key]) platform_cookies[key] = cookies[key];
    }
    try {
      const result = await api<Schema["SettingsResponse"]>("/settings", {
        method: "PUT",
        body: JSON.stringify({
          platform_cookies,
        } satisfies Schema["SettingsUpdate"]),
      });
      setCurrent(result.platform_cookies);
      setCookies({ xiaohongshu: "", xiaoheihe: "" });
      setClear({ xiaohongshu: false, xiaoheihe: false });
      setMessage("平台 Cookie 配置已保存，尚未验证登录有效性");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="settings-card" id="platforms">
      <div className="card-heading">
        <span className="feature-icon">
          <Icon name="lock" />
        </span>
        <div>
          <h2>平台 Cookie</h2>
          <p>管理小红书与小黑盒的登录凭据</p>
        </div>
      </div>
      <div className="notice">
        小红书与小黑盒采集会使用已保存的
        Cookie，可保存帖子正文、图片链接和顶层评论。
        保存配置不会自动验证登录有效性。
      </div>
      <form onSubmit={save}>
        <fieldset className="platform-fields" disabled={busy}>
          {platforms.map(
            ({ key, name, website, requestHost, loginRequest }) => (
              <div key={key} className="platform-field">
                <label htmlFor={`${key}-cookie`}>{name} Cookie</label>
                <input
                  id={`${key}-cookie`}
                  aria-describedby={`${key}-cookie-status`}
                  type="password"
                  value={cookies[key]}
                  onChange={(event) => {
                    setCookies({ ...cookies, [key]: event.target.value });
                    setMessage("");
                  }}
                  disabled={clear[key]}
                  maxLength={16384}
                  autoComplete="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder={
                    current[key].cookie_set
                      ? "留空保留，填写新值替换"
                      : "粘贴 Cookie 请求头的值"
                  }
                />
                <p className="cookie-status" id={`${key}-cookie-status`}>
                  {current[key].cookie_set ? "已保存，未验证" : "尚未配置"}
                </p>
                {current[key].cookie_set && (
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={clear[key]}
                      onChange={(event) => {
                        setClear({ ...clear, [key]: event.target.checked });
                        setMessage("");
                      }}
                    />
                    清除{name} Cookie
                  </label>
                )}
                <details className="cookie-help">
                  <summary>如何获取{name} Cookie</summary>
                  <ol>
                    <li>
                      在桌面浏览器登录
                      <a href={website} target="_blank" rel="noreferrer">
                        {name}官网
                      </a>
                      。
                    </li>
                    <li>
                      Chrome 按 F12 打开 Network（网络），选择
                      All（全部），在筛选框输入 <code>{requestHost}</code>{" "}
                      后刷新页面。
                    </li>
                    <li>
                      优先选择名称含 <code>{loginRequest}</code> 的请求，在
                      Headers → Request Headers（请求标头）中找到
                      Cookie（也可能显示为小写
                      cookie），复制冒号后的完整值。不要复制 Cookie:
                      前缀或响应中的 Set-Cookie，不需要自行拼接格式。
                    </li>
                    <li>
                      图片、脚本和 OPTIONS 请求可能不带 Cookie。找不到时，在
                      Application （应用）→ Storage → Cookies
                      下确认当前网站是否有登录记录；不要把 Cookie
                      值发到聊天或截图中。
                    </li>
                    <li>粘贴到上方输入框并保存。已保存的值不会再次显示。</li>
                  </ol>
                </details>
              </div>
            ),
          )}
          <p className="section-description">
            Cookie
            加密存储，仅供当前账号使用。它代表你的平台登录身份，请勿分享给他人。
          </p>
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
          {message && (
            <div className="notice success" role="status">
              {message}
            </div>
          )}
          <div className="form-bottom">
            <span>
              <Icon name="lock" size={14} /> 保存后清空输入框
            </span>
            <button className="button" disabled={busy || !changed}>
              {busy ? "保存中…" : "保存平台配置"}
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  );
}
