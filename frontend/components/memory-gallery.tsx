// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "@/lib/api";
import { changeNote } from "@/lib/notes";
import {
  dismissMemory,
  loadMemories,
  memorySwipe,
  type MemoryNote,
} from "@/lib/memory";
import { useAccount } from "./app-shell";
import { useNoteListSnapshot } from "./note-list-state";
import { CollectionDialog } from "./collection-dialog";
import { Icon } from "./icon";
import { MemoryCard } from "./memory-card";

export function MemoryGallery({ onClose }: { onClose: () => void }) {
  const user = useAccount();
  const snapshot = useNoteListSnapshot();
  const [notes, setNotes] = useState<MemoryNote[]>([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadedCount, setLoadedCount] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [round, setRound] = useState(0);
  const actionPending = useRef(false);
  const touch = useRef<{ x: number; y: number } | null>(null);
  const note = notes[index];

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError("");
    setMessage("");
    const timeout = setTimeout(() => controller.abort(), 10000);
    if (!navigator.onLine) {
      setError("回忆需要联网，请连接网络后重试。");
      setLoading(false);
      clearTimeout(timeout);
      return;
    }
    loadMemories(user.id, controller.signal)
      .then((items) => {
        if (active) {
          setNotes(items);
          setLoadedCount(items.length);
          setIndex(0);
        }
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      })
      .finally(() => {
        clearTimeout(timeout);
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [user.id, round]);

  const move = useCallback(
    (direction: number) => {
      if (actionPending.current || loading) return;
      setIndex((previous) =>
        Math.max(0, Math.min(notes.length, previous + direction)),
      );
      setError("");
      setMessage("");
    },
    [notes.length, loading],
  );

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (event.altKey || event.metaKey || event.ctrlKey || event.shiftKey)
        return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        move(event.key === "ArrowLeft" ? -1 : 1);
      }
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [move]);

  async function favorite(advance = false) {
    if (!note || actionPending.current) return;
    actionPending.current = true;
    setBusy(true);
    setError("");
    try {
      const value = advance || !note.is_favorite;
      await changeNote(note.id, "PATCH", { is_favorite: value });
      setNotes((items) =>
        items.map((item) =>
          item.id === note.id ? { ...item, is_favorite: value } : item,
        ),
      );
      if (snapshot.current)
        snapshot.current.items = snapshot.current.items.map((item) =>
          item.id === note.id ? { ...item, is_favorite: value } : item,
        );
      setMessage(value ? "已标记收藏" : "已取消收藏");
      if (advance) setIndex((previous) => previous + 1);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      actionPending.current = false;
      setBusy(false);
    }
  }

  async function dismiss() {
    if (!note || actionPending.current) return;
    actionPending.current = true;
    setBusy(true);
    setError("");
    try {
      if (!navigator.onLine) throw new TypeError("offline");
      await dismissMemory(note.id, user.id);
      setNotes((items) => items.filter((item) => item.id !== note.id));
      setMessage("已从回忆移除，30 天内不再推荐。笔记仍保留。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      actionPending.current = false;
      setBusy(false);
    }
  }

  return (
    <CollectionDialog title="回忆" onClose={onClose} className="memory-dialog">
      <div className="memory-stage">
        <p className="memory-intro">再读一次，让好想法重新生长。</p>
        {loading ? (
          <p role="status">正在寻找值得重访的笔记…</p>
        ) : (
          <>
            <div className="memory-progress" role="status" aria-live="polite">
              {note ? `${index + 1} / ${notes.length}` : ""}
            </div>
            {note && (
              <article
                className="memory-card"
                key={note.id}
                aria-label={`回忆笔记：${note.title || "无标题笔记"}`}
                onTouchStart={(event) => {
                  const point = event.touches[0];
                  touch.current =
                    event.touches.length === 1
                      ? { x: point.clientX, y: point.clientY }
                      : null;
                }}
                onTouchCancel={() => {
                  touch.current = null;
                }}
                onTouchEnd={(event) => {
                  const start = touch.current;
                  touch.current = null;
                  if (!start || actionPending.current) return;
                  const point = event.changedTouches[0];
                  const action = memorySwipe(
                    point.clientX - start.x,
                    point.clientY - start.y,
                  );
                  if (!action) return;
                  event.preventDefault();
                  if (action === "skip") move(1);
                  else void favorite(true);
                }}
              >
                <button
                  className="memory-dismiss icon-button"
                  aria-label="30 天内不再推荐"
                  title="30 天内不再推荐，笔记仍保留"
                  disabled={busy}
                  onClick={dismiss}
                >
                  ×
                </button>
                <MemoryCard note={note} />
                <div className="memory-actions">
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => move(1)}
                  >
                    跳过
                  </button>
                  <Link
                    className="button"
                    href={`/notes/?id=${note.id}`}
                    prefetch={false}
                  >
                    打开阅读 <Icon name="arrow" size={16} />
                  </Link>
                  <button
                    className="button secondary"
                    disabled={busy}
                    aria-pressed={note.is_favorite}
                    onClick={() => favorite()}
                  >
                    {note.is_favorite ? "★ 已收藏" : "☆ 收藏"}
                  </button>
                </div>
              </article>
            )}
            {!note && !error && (
              <section className="memory-card memory-empty">
                <Icon name="spark" size={40} />
                <h2>{loadedCount ? "已浏览全部" : "暂时没有适合重访的笔记"}</h2>
                <p>
                  {loadedCount
                    ? "把今天重拾的想法，带进下一次行动。"
                    : "回忆会挑选最近 7 天未打开、留有标注或摘要，或阅读超过两分钟的笔记。"}
                </p>
                <button
                  className="button"
                  onClick={() => setRound((value) => value + 1)}
                >
                  {loadedCount ? "再来一组" : "重新查找"}
                </button>
              </section>
            )}
            {index > 0 && (
              <button
                className="memory-previous"
                disabled={busy}
                onClick={() => move(-1)}
              >
                ← 上一篇
              </button>
            )}
          </>
        )}
        {error && (
          <p className="notice error" role="alert">
            {error}{" "}
            <button
              className="inline-button"
              disabled={busy}
              onClick={() => setRound((value) => value + 1)}
            >
              重新加载
            </button>
          </p>
        )}
        {message && (
          <p className="memory-message" role="status">
            {message}
          </p>
        )}
        <p className="memory-help">
          左滑跳过 · 右滑收藏并继续 · ← → 切换 · Esc 退出
        </p>
      </div>
    </CollectionDialog>
  );
}
