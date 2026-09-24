// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useState } from "react";
import { api, errorMessage, type Schema } from "@/lib/api";
import { connectionAvailable } from "@/lib/notes";

export function NoteSharing({ noteId }: { noteId: number }) {
  const [links, setLinks] = useState<Schema["ShareResponse"][]>([]);
  const [days, setDays] = useState("7");
  const [issued, setIssued] = useState<{ id: string; url: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const path = `/notes/${noteId}/shares`;
  useEffect(() => {
    let active = true;
    if (connectionAvailable())
      api<Schema["ShareResponse"][]>(path)
        .then((items) => {
          if (active) setLinks(items);
        })
        .catch((cause) => {
          if (active) setError(errorMessage(cause));
        });
    return () => {
      active = false;
    };
  }, [path]);
  async function create() {
    if (!connectionAvailable()) {
      setError("创建分享链接需要联网。");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const link = await api<Schema["IssuedShareResponse"]>(path, {
        method: "POST",
        body: JSON.stringify({
          expires_in_days: days === "never" ? null : Number(days),
        }),
      });
      setIssued({
        id: link.id,
        url: `${window.location.origin}/public/#${link.token}`,
      });
      setLinks(await api<Schema["ShareResponse"][]>(path));
      setMessage("分享链接已创建，请复制保存；离开页面后不会再显示完整链接。");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    setBusy(true);
    setError("");
    try {
      await api(`${path}/${id}`, { method: "DELETE" });
      setLinks((items) => items.filter((link) => link.id !== id));
      if (issued?.id === id) setIssued(null);
      setMessage("分享链接已撤销。");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="original-section share-controls" aria-label="公开分享">
      <details>
        <summary>公开分享这篇笔记</summary>
        <p>
          持有链接的人无需登录即可阅读标题、正文、摘要、来源、图片链接及全部已保存评论和评分。标签、收藏、保存选区和账号信息不会分享。请先确认内容适合公开。
        </p>
        <p className="muted">
          分享页展示当前内容，之后更新的摘要也会公开。可随时撤销，已被访客保存的副本无法收回。
        </p>
        <label>
          链接有效期{" "}
          <select
            value={days}
            onChange={(event) => setDays(event.target.value)}
          >
            <option value="1">1 天</option>
            <option value="7">7 天</option>
            <option value="30">30 天</option>
            <option value="never">永久（直到撤销）</option>
          </select>
        </label>{" "}
        <button
          className="button secondary small"
          disabled={busy}
          onClick={create}
        >
          确认内容可公开并创建链接
        </button>
        {issued && (
          <div>
            <label htmlFor="share-url">分享链接（仅本次显示）</label>
            <input
              id="share-url"
              readOnly
              value={issued.url}
              onFocus={(event) => event.target.select()}
            />
            <button
              className="inline-button"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(issued.url);
                  setMessage("链接已复制。");
                } catch {
                  setMessage("请选中上方链接并手动复制。");
                }
              }}
            >
              复制分享链接
            </button>
          </div>
        )}
        {links.length > 0 && (
          <ul className="share-links">
            {links.map((link) => (
              <li key={link.id}>
                <span>
                  {new Date(link.created_at).toLocaleString("zh-CN")} 创建 ·{" "}
                  {link.expires_at
                    ? `${new Date(link.expires_at).toLocaleString("zh-CN")} 到期`
                    : "永久有效"}
                </span>{" "}
                <button
                  className="inline-button danger"
                  disabled={busy}
                  onClick={() => revoke(link.id)}
                >
                  撤销链接
                </button>
              </li>
            ))}
          </ul>
        )}
        {message && <p role="status">{message}</p>}
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
      </details>
    </section>
  );
}
