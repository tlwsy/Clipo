"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell, useAccount } from "@/components/app-shell";
import { CaptureForm } from "@/components/capture-form";
import { Icon } from "@/components/icon";
import { api, errorMessage, type Schema } from "@/lib/api";

function Notes() {
  const user = useAccount();
  const [items, setItems] = useState<Schema["NoteItem"][]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async (next?: string) => {
    setBusy(true);
    setError("");
    try {
      const page = await api<Schema["NotePage"]>(
        `/notes?limit=24${next ? `&cursor=${encodeURIComponent(next)}` : ""}`,
      );
      setItems((previous) =>
        next ? [...previous, ...page.items] : page.items,
      );
      setCursor(page.next_cursor);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">COLLECT WHAT MATTERS</span>
          <h1>
            你的笔记<span className="greeting-dot">.</span>
          </h1>
          <p>{user.username}，让值得回看的内容，在这里慢慢积累。</p>
        </div>
        <Link className="button secondary small" href="/jobs/">
          查看保存队列
        </Link>
      </div>
      <CaptureForm />
      <div className="section-heading">
        <h2>最近收藏</h2>
        <button
          className="inline-button"
          disabled={busy}
          onClick={() => load()}
        >
          刷新列表
        </button>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
          <button
            className="inline-button"
            onClick={() => load(cursor ?? undefined)}
          >
            重试
          </button>
        </div>
      )}
      {!busy && !error && items.length === 0 && (
        <section className="empty-state">
          <Icon name="bookmark" size={40} />
          <h2>第一篇好内容，从一个链接开始</h2>
          <p>保存公开网页后，你可以在这里阅读正文、摘要和要点。</p>
          <Link className="text-link" href="/settings/#llm">
            配置 AI 摘要 <Icon name="arrow" size={15} />
          </Link>
        </section>
      )}
      <div className="notes-grid">
        {items.map((note) => (
          <Link
            href={`/notes/?id=${note.id}`}
            className="note-card"
            key={note.id}
          >
            <div className="note-card-meta">
              <span>{new URL(note.url).hostname}</span>
              <span>
                {note.status === "ready" ? "AI 已整理" : "未生成摘要"}
              </span>
            </div>
            <h2>{note.title}</h2>
            <p>{note.summary_excerpt}</p>
            <div className="note-card-footer">
              <span>{note.author || "网页收藏"}</span>
              <time>
                {new Date(note.created_at).toLocaleDateString("zh-CN")}
              </time>
            </div>
          </Link>
        ))}
      </div>
      {busy && (
        <p className="list-status" role="status">
          正在读取笔记…
        </p>
      )}
      {cursor && (
        <button
          className="button secondary load-more"
          disabled={busy}
          onClick={() => load(cursor)}
        >
          加载更多
        </button>
      )}
    </>
  );
}
export default function HomePage() {
  return (
    <AppShell>
      <Notes />
    </AppShell>
  );
}
