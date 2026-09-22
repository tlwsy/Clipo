"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { CaptureForm } from "@/components/capture-form";
import { localCaptures } from "@/lib/notes";
import { api, ApiError, errorMessage, type Schema } from "@/lib/api";

const labels: Record<Schema["JobResponse"]["status"], string> = {
  uploading: "正在上传页面",
  queued: "等待处理",
  running: "正在整理",
  retrying: "等待自动重试",
  failed: "保存失败",
  success: "已保存",
};

function Queue() {
  const [items, setItems] = useState<Schema["JobResponse"][]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [retrying, setRetrying] = useState<string | null>(null);
  const fetching = useRef(false);
  const currentItems = useRef(items);
  const load = useCallback(async (next?: string, poll = false) => {
    if (fetching.current) return;
    fetching.current = true;
    if (!poll) setBusy(true);
    try {
      if (
        poll &&
        navigator.onLine &&
        !currentItems.current.some((job) => job.job_id.startsWith("offline:"))
      ) {
        const active = currentItems.current.filter((job) =>
          ["uploading", "queued", "running", "retrying"].includes(job.status),
        );
        const updates = await Promise.all(
          active.map((job) =>
            api<Schema["JobResponse"]>(`/jobs/${job.job_id}`),
          ),
        );
        setItems((previous) =>
          previous.map(
            (job) =>
              updates.find((update) => update.job_id === job.job_id) ?? job,
          ),
        );
      } else {
        const page = await api<Schema["JobPage"]>(
          `/jobs?limit=25${next ? `&cursor=${encodeURIComponent(next)}` : ""}`,
        );
        setItems((previous) =>
          next ? [...previous, ...page.items] : page.items,
        );
        setCursor(page.next_cursor);
      }
      setError("");
    } catch (cause) {
      if (!(cause instanceof ApiError)) {
        setItems(await localCaptures().catch(() => []));
        setCursor(null);
        setError("离线时仅显示本机待提交链接，联网后可查看处理进度。");
      } else setError(errorMessage(cause));
    } finally {
      fetching.current = false;
      if (!poll) setBusy(false);
    }
  }, []);
  useEffect(() => {
    currentItems.current = items;
  }, [items]);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      if (!document.hidden) void load(undefined, true);
    }, 2500);
    const synced = () => {
      void load();
    };
    window.addEventListener("clipo:synced", synced);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("clipo:synced", synced);
    };
  }, [load]);
  async function retry(id: string) {
    setRetrying(id);
    setError("");
    try {
      const job = await api<Schema["JobResponse"]>(`/jobs/${id}/retry`, {
        method: "POST",
      });
      setItems((previous) =>
        previous.map((item) => (item.job_id === id ? job : item)),
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setRetrying(null);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">SAVED, STEP BY STEP</span>
          <h1>
            保存队列<span className="greeting-dot">.</span>
          </h1>
          <p>提交后即可离开，内容会继续在后台整理。</p>
        </div>
        <Link href="/" className="button secondary small">
          返回笔记
        </Link>
      </div>
      <CaptureForm />
      <div className="section-heading">
        <h2>保存记录</h2>
        <button
          className="inline-button"
          disabled={busy}
          onClick={() => load()}
        >
          刷新队列
        </button>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
          <button className="inline-button" onClick={() => load()}>
            重新加载
          </button>
        </div>
      )}
      {!busy && !error && !items.length && (
        <section className="empty-state">
          <h2>还没有保存记录</h2>
          <p>粘贴一个网页链接，开始你的第一次收藏。</p>
        </section>
      )}
      <div className="job-list">
        {items.map((job) => (
          <article className="job-card" key={job.job_id}>
            <div className="job-top">
              <span className={`job-status ${job.status}`}>
                {labels[job.status]}
              </span>
              <time>{new Date(job.created_at).toLocaleString("zh-CN")}</time>
            </div>
            <a
              className="job-url"
              href={job.url}
              target="_blank"
              rel="noreferrer"
            >
              {job.url}
            </a>
            <div className="job-detail">
              <span>
                已尝试 {job.attempts} 次{job.cached ? " · 使用已提取内容" : ""}
              </span>
              {job.next_retry_at && (
                <span>
                  下次重试：
                  {new Date(job.next_retry_at).toLocaleTimeString("zh-CN")}
                </span>
              )}
            </div>
            {job.last_error && (
              <p
                className={job.status === "failed" ? "notice error" : "notice"}
              >
                {job.last_error}
              </p>
            )}
            {job.status === "failed" && (
              <button
                className="button secondary small"
                disabled={retrying !== null}
                onClick={() => retry(job.job_id)}
              >
                {retrying === job.job_id ? "提交中…" : "重新保存"}
              </button>
            )}
            {job.note_id && (
              <Link className="text-link" href={`/notes/?id=${job.note_id}`}>
                阅读笔记 →
              </Link>
            )}
            {job.status === "success" && !job.note_id && (
              <p className="muted">笔记已删除</p>
            )}
          </article>
        ))}
      </div>
      {busy && (
        <p className="list-status" role="status">
          正在读取队列…
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
export default function JobsPage() {
  return (
    <AppShell>
      <Queue />
    </AppShell>
  );
}
