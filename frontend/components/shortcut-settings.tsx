// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, errorMessage, type Schema } from "@/lib/api";
import {
  copySetupInput,
  createShortcutPairing,
  pairingExpired,
} from "@/lib/shortcuts";
import { useAccount } from "./app-shell";
import { Icon } from "./icon";

export function ShortcutSettings() {
  const user = useAccount();
  const [info, setInfo] = useState<Schema["ShortcutInfo"] | null>(null);
  const [server, setServer] = useState("");
  const [name, setName] = useState("我的 iPhone");
  const [pairing, setPairing] = useState<Schema["IssuedPairing"] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setServer(window.location.origin);
    void api<Schema["ShortcutInfo"]>("/shortcuts/info", {
      authenticated: false,
    })
      .then(setInfo)
      .catch((cause) => setError(errorMessage(cause)));
  }, []);

  const identifier = pairing?.id;
  const status = pairing?.status;
  const expiresAt = pairing?.expires_at;
  useEffect(() => {
    if (!identifier) return;
    let active = true;
    let checking = false;
    const controller = new AbortController();
    async function check() {
      if (checking || !active) return;
      if (
        status === "pending" &&
        expiresAt &&
        Date.parse(expiresAt) <= Date.now()
      ) {
        setPairing((current) =>
          current && current.id === identifier
            ? { ...current, status: "expired", setup_input: "", launch_url: "" }
            : current,
        );
        return;
      }
      checking = true;
      try {
        const result = await api<Schema["PairingStatus"]>(
          `/shortcuts/pairings/${identifier}`,
          {
            expectedUserId: user.id,
            signal: controller.signal,
          },
        );
        if (!active) return;
        setPairing((current) =>
          current && current.id === identifier
            ? {
                ...current,
                ...result,
                ...(result.status !== "pending"
                  ? { setup_input: "", launch_url: "" }
                  : {}),
              }
            : current,
        );
        setError("");
        if (result.status === "claimed" && status !== "claimed") {
          window.dispatchEvent(new Event("clipo:tokens-changed"));
        }
      } catch (cause) {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 404) {
          setPairing(null);
          setMessage("此配置已取消或被替换，请重新生成。");
        } else {
          setError(
            "暂时无法确认领取状态，请保持联网；不要重复配置同一个设备。",
          );
        }
      } finally {
        checking = false;
      }
    }
    const timer =
      status === "pending"
        ? window.setInterval(() => void check(), 3000)
        : undefined;
    window.addEventListener("focus", check);
    window.addEventListener("clipo:tokens-changed", check);
    return () => {
      active = false;
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener("focus", check);
      window.removeEventListener("clipo:tokens-changed", check);
    };
  }, [identifier, status, expiresAt, user.id]);

  async function generate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    setCopied(false);
    try {
      setPairing(await createShortcutPairing(name.trim(), user.id));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!pairing) return;
    setBusy(true);
    setError("");
    try {
      await api(`/shortcuts/pairings/${pairing.id}`, {
        method: "DELETE",
        expectedUserId: user.id,
      });
      setPairing(null);
      setMessage("配置已取消，未创建新的设备 Token。");
    } catch (cause) {
      setError(errorMessage(cause));
      window.dispatchEvent(new Event("clipo:tokens-changed"));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!pairing || pairingExpired(pairing) || pairing.status !== "pending")
      return;
    const success = await copySetupInput(pairing.setup_input);
    setCopied(success);
    if (!success) setError("未能自动复制，请展开下面的配置文本并长按复制。");
  }

  const pending = pairing?.status === "pending" && !pairingExpired(pairing);
  return (
    <section className="settings-card shortcut-settings" id="shortcut">
      <div className="card-heading">
        <span className="feature-icon lavender">
          <Icon name="clip" />
        </span>
        <div>
          <h2>iPhone 快捷指令</h2>
          <p>复制帖子链接，也能一键保存</p>
        </div>
      </div>
      <p className="section-description">
        先安装自动配置版“保存到
        Clipo”，再为这台手机生成配置。小红书、小黑盒只提供复制链接时，复制后运行快捷指令即可。
      </p>
      <div className="shortcut-actions">
        {info?.install_url && (
          <a
            className="button secondary"
            href={info.install_url}
            target="_blank"
            rel="noreferrer"
          >
            安装快捷指令
          </a>
        )}
        <Link className="button secondary" href="/shortcuts/">
          安装与使用指南
        </Link>
      </div>
      {info && !info.install_url && (
        <div className="notice">
          通用版安装链接尚未发布。先按指南导入或创建新版；旧的固定地址版无法接收自动配置。
        </div>
      )}
      <p className="shortcut-server">
        连接到 <strong>{server || "当前服务器"}</strong>
      </p>
      {server.startsWith("http:") && (
        <p className="section-description">
          当前为 HTTP 本机或局域网测试入口；正式使用请通过 HTTPS 访问。
        </p>
      )}
      <form className="token-form" onSubmit={generate}>
        <label>
          设备名称
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={100}
            placeholder="例如：我的 iPhone"
          />
        </label>
        <button className="button" disabled={busy || !name.trim()}>
          {busy ? "处理中…" : pairing ? "重新生成配置" : "生成设备配置"}
        </button>
      </form>
      <p className="shortcut-help">
        配置有效 5
        分钟，只能领取一次。重新生成会使本账号之前未领取的配置失效，已连接设备继续可用。
      </p>
      {pending && pairing && (
        <div className="token-reveal shortcut-pairing">
          <strong>配置已准备好</strong>
          <p>
            请在 {new Date(pairing.expires_at).toLocaleTimeString()} 前，用这台
            iPhone 打开快捷指令并确认保存。
          </p>
          <div className="shortcut-actions">
            <a
              className="button"
              href={pairing.launch_url}
              onClick={(event) => {
                if (busy || pairingExpired(pairing)) event.preventDefault();
              }}
            >
              打开快捷指令并配置
            </a>
            <button
              type="button"
              className="inline-button"
              onClick={cancel}
              disabled={busy}
            >
              取消配置
            </button>
          </div>
          <details>
            <summary>没有自动打开？</summary>
            <p>
              确认已安装新版且名称为“保存到
              Clipo”。也可以复制配置文本，然后手动运行新版指令。此文本允许领取设备凭据，请勿转发。
            </p>
            <button
              type="button"
              className="button secondary small"
              onClick={copy}
              disabled={busy}
            >
              {copied ? "已复制配置" : "复制配置文本"}
            </button>
            <label>
              配置文本
              <textarea
                readOnly
                value={pairing.setup_input}
                rows={4}
                spellCheck={false}
                onFocus={(event) => event.currentTarget.select()}
              />
            </label>
          </details>
        </div>
      )}
      {pairing?.status === "claimed" && (
        <div className="notice success" role="status">
          设备已领取配置，请在快捷指令中完成文件保存。随后复制帖子链接并运行指令即可。设备
          Token 可在下方列表撤销。
        </div>
      )}
      {pairing && pairingExpired(pairing) && (
        <div className="notice" role="status">
          配置已过期，请重新生成。
        </div>
      )}
      {pairing?.status === "revoked" && (
        <div className="notice" role="status">
          这个设备的 Token 已撤销。如需继续使用，请重新生成配置。
        </div>
      )}
      {message && (
        <div className="notice" role="status">
          {message}
        </div>
      )}
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}
