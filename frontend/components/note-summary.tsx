// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, type Schema } from "@/lib/api";
import { connectionAvailable, loadNote } from "@/lib/notes";
import { captureKey } from "@/lib/share";

const labels = {
  queued: "摘要任务等待处理",
  running: "正在重新生成摘要",
  retrying: "摘要生成暂时失败，等待自动重试",
  failed: "摘要生成失败，已有内容已保留",
  success: "摘要已更新",
};

export function NoteSummary({
  noteId,
  onChange,
}: {
  noteId: number;
  onChange: (note: Schema["NoteResponse"]) => void;
}) {
  const [job, setJob] = useState<Schema["SummaryJobResponse"] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef<string | null>(null);
  const changed = useRef(onChange);
  changed.current = onChange;
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let lastCompleted: string | null = null;
    async function refresh() {
      try {
        if (!connectionAvailable()) return;
        const current = await api<Schema["SummaryJobResponse"] | null>(
          `/notes/${noteId}/summary-job`,
        );
        if (!active) return;
        setJob(current);
        if (
          current?.status === "success" &&
          current.updated_at !== lastCompleted
        ) {
          const note = await loadNote(noteId);
          if (active) changed.current(note);
          lastCompleted = current.updated_at;
        }
      } catch (cause) {
        if (active) setError(errorMessage(cause));
      } finally {
        if (active) timer = setTimeout(refresh, 3000);
      }
    }
    void refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [noteId]);

  async function submit(retry: boolean) {
    if (!connectionAvailable()) {
      setError("重新生成摘要需要联网，请连接服务后重试。");
      return;
    }
    setBusy(true);
    setError("");
    key.current ??= captureKey();
    try {
      const current = await api<Schema["SummaryJobResponse"]>(
        retry && job
          ? `/summary-jobs/${job.id}/retry`
          : `/notes/${noteId}/summarize`,
        {
          method: "POST",
          body: retry
            ? undefined
            : JSON.stringify({ request_key: key.current }),
        },
      );
      setJob(current);
      key.current = null;
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  const pending = job && ["queued", "running", "retrying"].includes(job.status);
  return (
    <section className="original-section" aria-label="重新生成摘要">
      <button
        className="inline-button"
        disabled={busy || !!pending}
        onClick={() => submit(job?.status === "failed")}
      >
        {busy
          ? "提交中…"
          : job?.status === "failed"
            ? "重试摘要"
            : "重新生成摘要"}
      </button>
      <p className="muted">
        使用当前模型设置处理已保存原文与评论，可能产生模型费用；成功后更新本篇摘要，失败保留已有内容。
      </p>
      {job && (
        <p role="status">
          {labels[job.status]}
          {job.last_error ? `：${job.last_error}` : ""}
        </p>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
