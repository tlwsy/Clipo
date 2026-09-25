// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { ArticleContent } from "@/components/article-content";
import { api, errorMessage, type Schema } from "@/lib/api";

export default function PublicNotePage() {
  const [note, setNote] = useState<Schema["PublicNoteResponse"] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    async function read() {
      clearTimeout(timer);
      controller?.abort();
      controller = new AbortController();
      const current = controller;
      const token = window.location.hash.slice(1);
      if (!/^[A-Za-z0-9_-]{43}$/.test(token)) {
        setNote(null);
        setError("分享链接不完整，请使用分享者提供的完整链接。");
        return;
      }
      try {
        const result = await api<Schema["PublicNoteResponse"]>(
          "/public/notes/read",
          {
            authenticated: false,
            method: "POST",
            body: JSON.stringify({ token }),
            signal: current.signal,
          },
        );
        if (active && !current.signal.aborted) {
          setNote(result);
          setError("");
        }
      } catch (cause) {
        if (active && !current.signal.aborted) {
          setNote(null);
          setError(errorMessage(cause));
        }
      } finally {
        if (active && !current.signal.aborted) timer = setTimeout(read, 30000);
      }
    }
    const changed = () => {
      setNote(null);
      void read();
    };
    const visibility = () => {
      if (document.visibilityState === "visible") changed();
      else {
        setNote(null);
        controller?.abort();
        clearTimeout(timer);
      }
    };
    void read();
    window.addEventListener("hashchange", changed);
    window.addEventListener("pageshow", changed);
    window.addEventListener("offline", changed);
    window.addEventListener("online", changed);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      active = false;
      clearTimeout(timer);
      controller?.abort();
      window.removeEventListener("hashchange", changed);
      window.removeEventListener("pageshow", changed);
      window.removeEventListener("offline", changed);
      window.removeEventListener("online", changed);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  return (
    <main className="public-reader">
      <Link href="/" className="brand">
        Clipo<span>.</span>
      </Link>
      <p className="muted">公开分享 · 只读笔记</p>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {!note && !error && <p role="status">正在读取分享内容…</p>}
      {note && (
        <article className="reader">
          <header>
            <h1>{note.title || "无标题笔记"}</h1>
            <div className="reader-meta">
              {note.author && <span>{note.author}</span>}
              {note.url && (
                <a href={note.url} target="_blank" rel="noreferrer noopener">
                  查看原网页 ↗
                </a>
              )}
            </div>
          </header>
          {note.summary_markdown && (
            <section className="summary-section">
              <span className="pill">AI 整理</span>
              <div className="markdown">
                <Markdown
                  skipHtml
                  components={{
                    a: ({ children, ...props }) => (
                      <a {...props} target="_blank" rel="noreferrer noopener">
                        {children}
                      </a>
                    ),
                    img: ({ src }) => (
                      <a href={src} target="_blank" rel="noreferrer noopener">
                        查看引用图片
                      </a>
                    ),
                  }}
                >
                  {note.summary_markdown}
                </Markdown>
              </div>
              {note.key_points.length > 0 && (
                <>
                  <h2>值得记住的要点</h2>
                  <ul className="key-points">
                    {note.key_points.map((point, index) => (
                      <li key={index}>{point}</li>
                    ))}
                  </ul>
                </>
              )}
            </section>
          )}
          <section className="original-section">
            <h2>原始正文</h2>
            <ArticleContent
              text={note.text}
              blocks={note.blocks}
              images={note.images}
              publicView
            />
          </section>
          {note.comments.length > 0 && (
            <section className="original-section">
              <h2>评论</h2>
              {note.comments.map((comment, index) => (
                <div className="comment" key={index}>
                  <strong>{comment.author || "匿名"}</strong>
                  {comment.is_valuable && <span className="pill">高价值</span>}
                  <p>{comment.content}</p>
                  <small>
                    {comment.likes} 赞 · {comment.replies} 回复 ·{" "}
                    {comment.ai_score === null
                      ? "未评分"
                      : `AI 评分 ${comment.ai_score}`}
                  </small>
                  {comment.ai_reason && (
                    <p className="muted">{comment.ai_reason}</p>
                  )}
                </div>
              ))}
            </section>
          )}
        </article>
      )}
    </main>
  );
}
