// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";

import { useEffect, useState, type FormEvent } from "react";

import { useAccount } from "@/components/app-shell";
import { CaptureSettings } from "@/components/capture-settings";
import { BackupSettings } from "@/components/backup-settings";
import { Icon } from "@/components/icon";
import { ModelSettings } from "@/components/model-settings";
import { PlatformSettings } from "@/components/platform-settings";
import { ShortcutSettings } from "@/components/shortcut-settings";
import { api, errorMessage, type Schema } from "@/lib/api";

function TokenSettings({ initial }: { initial: Schema["TokenResponse"][] }) {
  const [tokens, setTokens] = useState(initial);
  const [name, setName] = useState("");
  const [issued, setIssued] = useState<Schema["IssuedTokenResponse"] | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      void api<Schema["TokenResponse"][]>("/tokens")
        .then((result) => {
          if (active) setTokens(result);
        })
        .catch(() => undefined);
    };
    window.addEventListener("focus", refresh);
    window.addEventListener("clipo:tokens-changed", refresh);
    return () => {
      active = false;
      window.removeEventListener("focus", refresh);
      window.removeEventListener("clipo:tokens-changed", refresh);
    };
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<Schema["IssuedTokenResponse"]>("/tokens", {
        method: "POST",
        body: JSON.stringify({ name } satisfies Schema["TokenRequest"]),
      });
      setIssued(result);
      setTokens([result, ...tokens]);
      setName("");
      setCopied(false);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: number) {
    setRemoving(id);
    setError("");
    try {
      await api<void>(`/tokens/${id}`, { method: "DELETE" });
      setTokens(tokens.filter((token) => token.id !== id));
      if (issued?.id === id) setIssued(null);
      setConfirm(null);
      window.dispatchEvent(new Event("clipo:tokens-changed"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setRemoving(null);
    }
  }

  async function copy() {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.token);
      setCopied(true);
    } catch {
      setError("无法访问剪贴板，请选中令牌后手动复制");
    }
  }

  return (
    <section className="settings-card" id="tokens">
      <div className="card-heading">
        <span className="feature-icon lavender">
          <Icon name="key" />
        </span>
        <div>
          <h2>API Token</h2>
          <p>独立管理客户端的访问凭据</p>
        </div>
      </div>
      <p className="section-description">
        令牌可代表你的账号调用
        API，请只交给你信任的客户端。每个客户端使用一个令牌，方便单独撤销。
      </p>
      {issued && (
        <div className="token-reveal" role="status">
          <strong>请保存「{issued.name}」的令牌</strong>
          <p>完整令牌仅在创建时显示一次。</p>
          <code>{issued.token}</code>
          <div>
            <button
              type="button"
              className="button secondary small"
              onClick={copy}
            >
              {copied ? "已复制" : "复制令牌"}
            </button>
            <button
              type="button"
              className="inline-button"
              onClick={() => setIssued(null)}
            >
              我已保存
            </button>
          </div>
        </div>
      )}
      <form className="token-form" onSubmit={create}>
        <label>
          令牌名称
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            placeholder="例如：我的浏览器"
          />
        </label>
        <button
          className="button"
          disabled={busy || removing !== null || !name.trim()}
        >
          {busy ? "创建中…" : "创建令牌"}
        </button>
      </form>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {tokens.length === 0 ? (
        <div className="empty-tokens">
          <Icon name="key" size={26} />
          <p>还没有访问令牌</p>
          <span>需要连接其他客户端时，在这里创建一个。</span>
        </div>
      ) : (
        <ul className="token-list">
          {tokens.map((token) => (
            <li key={token.id}>
              <div>
                <strong>{token.name}</strong>
                <small>
                  创建于{" "}
                  {new Date(token.created_at).toLocaleDateString("zh-CN")} ·{" "}
                  {token.last_used_at
                    ? `最近使用 ${new Date(token.last_used_at).toLocaleDateString("zh-CN")}`
                    : "尚未使用"}
                </small>
              </div>
              <div className="token-actions">
                {confirm === token.id ? (
                  <>
                    <button
                      className="inline-button danger"
                      disabled={removing !== null || busy}
                      onClick={() => revoke(token.id)}
                    >
                      {removing === token.id ? "撤销中…" : "确认撤销"}
                    </button>
                    <button
                      className="inline-button"
                      disabled={removing !== null}
                      onClick={() => setConfirm(null)}
                    >
                      取消
                    </button>
                  </>
                ) : (
                  <button
                    className="inline-button danger"
                    disabled={removing !== null || busy}
                    onClick={() => setConfirm(token.id)}
                  >
                    撤销
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SettingsContent() {
  const user = useAccount();
  const [data, setData] = useState<{
    settings: Schema["SettingsResponse"];
    tokens: Schema["TokenResponse"][];
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Schema["SettingsResponse"]>("/settings"),
      api<Schema["TokenResponse"][]>("/tokens"),
    ])
      .then(([settings, tokens]) => {
        if (active) setData({ settings, tokens });
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">MAKE IT YOURS</span>
          <h1>
            空间设置<span className="greeting-dot">.</span>
          </h1>
          <p>按你的习惯，照顾好这个小小的知识空间。</p>
        </div>
      </div>
      <div className="settings-layout">
        <div className="settings-main">
          {error && (
            <div className="notice error" role="alert">
              {error}{" "}
              <button
                className="inline-button"
                onClick={() => location.reload()}
              >
                重新加载
              </button>
            </div>
          )}
          {data ? (
            <>
              <ModelSettings initial={data.settings.llm} />
              <CaptureSettings initial={data.settings.capture} />
              <PlatformSettings initial={data.settings.platform_cookies} />
              <ShortcutSettings />
              <BackupSettings />
              <TokenSettings initial={data.tokens} />
            </>
          ) : (
            !error && <p role="status">正在读取设置…</p>
          )}
        </div>
        <aside className="settings-aside">
          <div className="profile-card">
            <span className="avatar large">
              {user.username.slice(0, 1).toUpperCase()}
            </span>
            <h3>{user.username}</h3>
            <p>{user.email}</p>
            <span className="subtle-badge">
              {user.is_admin ? "空间管理员" : "空间成员"}
            </span>
          </div>
          <div className="settings-tip">
            <Icon name="lock" size={22} />
            <h3>属于你的空间</h3>
            <p>
              配置按账号独立保存。API Key 与平台 Cookie
              加密存储，访问令牌可以随时撤销。
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}

export default function SettingsPage() {
  return (
    <>
      <SettingsContent />
    </>
  );
}
