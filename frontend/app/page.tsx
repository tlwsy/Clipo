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
  const [tags, setTags] = useState<Schema["TagResponse"][]>([]);
  const [tag, setTag] = useState("");
  const [favorite, setFavorite] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(
    async (next?: string) => {
      setBusy(true);
      setError("");
      try {
        const page = await api<Schema["NotePage"]>(
          `/notes?limit=24${tag ? `&tag_id=${tag}` : ""}${favorite ? "&favorite=true" : ""}${next ? `&cursor=${encodeURIComponent(next)}` : ""}`,
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
    },
    [tag, favorite],
  );
  useEffect(() => {
    api<Schema["TagResponse"][]>("/tags")
      .then(setTags)
      .catch((cause) => setError(errorMessage(cause)));
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
      <div className="note-filters">
        <label>
          标签
          <select
            aria-label="按标签筛选"
            value={tag}
            onChange={(event) => setTag(event.target.value)}
          >
            <option value="">全部标签</option>
            {tags.map((item) => (
              <option value={item.id} key={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={favorite}
            onChange={(event) => setFavorite(event.target.checked)}
          />
          只看收藏
        </label>
        {tag && (
          <button
            className="inline-button danger"
            onClick={async () => {
              if (
                !window.confirm(
                  "删除此标签？所有笔记上的这个标签都会移除，笔记会保留。",
                )
              )
                return;
              try {
                await api(`/tags/${tag}`, { method: "DELETE" });
                setTags(tags.filter((item) => String(item.id) !== tag));
                setTag("");
              } catch (cause) {
                setError(errorMessage(cause));
              }
            }}
          >
            删除此标签
          </button>
        )}
      </div>
      <div className="section-heading">
        <h2>最近笔记</h2>
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
          <h2>还没有符合条件的笔记</h2>
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
            <h2>
              {note.is_favorite ? "★ " : ""}
              {note.title || "无标题笔记"}
            </h2>
            <div className="tag-list">
              {note.tags.map((item) => (
                <span className="subtle-badge" key={item.id}>
                  {item.name}
                </span>
              ))}
            </div>
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
