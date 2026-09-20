"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Markdown from "react-markdown";
import { AppShell } from "@/components/app-shell";
import { api, errorMessage, type Schema } from "@/lib/api";

function Reader() {
  const [note, setNote] = useState<Schema["NoteResponse"] | null>(null);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const router = useRouter();
  useEffect(() => {
    let active = true;
    const id = new URLSearchParams(window.location.search).get("id");
    if (!id || !/^\d+$/.test(id)) {
      setError("笔记地址不完整，请返回列表重新打开。");
      return;
    }
    api<Schema["NoteResponse"]>(`/notes/${id}`)
      .then((data) => {
        if (active) setNote(data);
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      });
    return () => {
      active = false;
    };
  }, []);
  async function remove() {
    if (!note) return;
    setDeleting(true);
    setError("");
    try {
      await api<void>(`/notes/${note.id}`, { method: "DELETE" });
      router.replace("/");
    } catch (cause) {
      setError(errorMessage(cause));
      setDeleting(false);
    }
  }
  return (
    <>
      <div className="reader-toolbar">
        <Link href="/" className="text-link">
          ← 全部笔记
        </Link>
        {note && (
          <div>
            {confirm ? (
              <>
                <span>删除这篇笔记及评论？</span>
                <button
                  className="inline-button danger"
                  disabled={deleting}
                  onClick={remove}
                >
                  {deleting ? "删除中…" : "确认删除"}
                </button>
                <button
                  className="inline-button"
                  disabled={deleting}
                  onClick={() => setConfirm(false)}
                >
                  取消
                </button>
              </>
            ) : (
              <button
                className="inline-button danger"
                onClick={() => setConfirm(true)}
              >
                删除笔记
              </button>
            )}
          </div>
        )}
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {!note && !error && <p role="status">正在打开笔记…</p>}
      {note && (
        <article className="reader">
          <header>
            <span className="eyebrow">KEEP THE GOOD IDEAS</span>
            <h1>{note.title}</h1>
            <div className="reader-meta">
              <span>{note.source.author || "网页收藏"}</span>
              <time>
                {new Date(note.created_at).toLocaleDateString("zh-CN")} 保存
              </time>
              {note.source.published_at && (
                <span>
                  {new Date(note.source.published_at).toLocaleDateString(
                    "zh-CN",
                  )}{" "}
                  发布
                </span>
              )}
              <a href={note.url} target="_blank" rel="noreferrer">
                查看原网页 ↗
              </a>
            </div>
          </header>
          {note.status === "original_only" ? (
            <div className="notice">
              {note.summary_error || "未生成摘要，原文已保存。"}{" "}
              <Link className="inline-button" href="/settings/#llm">
                模型设置
              </Link>
            </div>
          ) : (
            <section className="summary-section">
              <span className="pill">AI 整理</span>
              <div className="markdown">
                <Markdown
                  skipHtml
                  components={{
                    a: ({ children, ...props }) => (
                      <a {...props} target="_blank" rel="noreferrer">
                        {children}
                      </a>
                    ),
                    img: ({ src }) => (
                      <a href={src} target="_blank" rel="noreferrer">
                        查看引用图片
                      </a>
                    ),
                  }}
                >
                  {note.summary_markdown ?? ""}
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
              {note.suggested_tags.length > 0 && (
                <div className="suggested-tags">
                  <span>建议标签</span>
                  {note.suggested_tags.map((tag, index) => (
                    <span className="subtle-badge" key={index}>
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </section>
          )}
          <section className="original-section">
            <h2>原始正文</h2>
            <div className="original-text">{note.content.text}</div>
          </section>
          {(note.content.images ?? []).length > 0 && (
            <section className="original-section">
              <h2>原文图片</h2>
              <p className="muted">图片链接指向原网站。</p>
              <ul>
                {note.content.images?.map((url, index) => (
                  <li key={index}>
                    <a
                      className="text-link"
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看图片 {index + 1} ↗
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {note.comments.length > 0 && (
            <section className="original-section">
              <h2>评论</h2>
              {note.comments.map((comment) => (
                <div className="comment" key={comment.id}>
                  <strong>{comment.author || "匿名"}</strong>
                  <p>{comment.content}</p>
                  <small>
                    {comment.likes} 赞 · {comment.replies} 回复
                  </small>
                </div>
              ))}
            </section>
          )}
        </article>
      )}
    </>
  );
}
export default function NotePage() {
  return (
    <AppShell>
      <Reader />
    </AppShell>
  );
}
