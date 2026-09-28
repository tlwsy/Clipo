// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Markdown from "react-markdown";
import { NoteComments } from "@/components/note-comments";
import { ArticleContent } from "@/components/article-content";
import { NoteOrganization } from "@/components/note-organization";
import { NoteSummary } from "@/components/note-summary";
import { NoteSharing } from "@/components/note-sharing";
import { useNoteListSnapshot } from "@/components/note-list-state";
import { loadNote, changeNote } from "@/lib/notes";
import { errorMessage, type Schema } from "@/lib/api";
import { sourceName } from "@/lib/source-name";

function Reader() {
  const snapshot = useNoteListSnapshot();
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
    loadNote(Number(id))
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
      await changeNote(note.id, "DELETE");
      if (snapshot.current)
        snapshot.current.items = snapshot.current.items.filter(
          (item) => item.id !== note.id,
        );
      router.replace("/", { scroll: false });
    } catch (cause) {
      setError(errorMessage(cause));
      setDeleting(false);
    }
  }
  return (
    <>
      <div className="reader-toolbar">
        <Link href="/" scroll={false} className="text-link">
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
            <h1>{note.title || "无标题笔记"}</h1>
            <div className="reader-meta">
              <span>{sourceName({ ...note.source, url: note.url })}</span>
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
          <NoteOrganization note={note} onChange={setNote} />
          <NoteSummary noteId={note.id} onChange={setNote} />
          <NoteSharing noteId={note.id} />
          {(note.content.capture_warnings ?? []).map((warning, index) => (
            <p className="notice" role="status" key={index}>
              {warning}
            </p>
          ))}
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
            </section>
          )}
          <section className="original-section">
            <h2>原始正文</h2>
            <ArticleContent
              text={note.content.text}
              blocks={note.content.blocks}
              images={note.content.images}
            />
          </section>
          {note.content.selection && (
            <section className="original-section">
              <h2>保存时的选区</h2>
              <p className="original-text">{note.content.selection}</p>
            </section>
          )}
          {(note.comments.length > 0 ||
            ["xiaohongshu", "xiaoheihe", "bilibili", "youtube"].includes(
              note.source.platform,
            )) && <NoteComments note={note} />}
        </article>
      )}
    </>
  );
}
export default function NotePage() {
  return (
    <>
      <Reader />
    </>
  );
}
