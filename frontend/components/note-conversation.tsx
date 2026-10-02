// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { errorMessage } from "@/lib/api";
import { captureKey } from "@/lib/share";
import {
  askQuestion,
  conversationPending,
  loadConversation,
  mergeMessages,
  retryQuestion,
  type History,
} from "@/lib/conversations";
import { useAccount } from "./app-shell";
import { ConversationMessage } from "./conversation-message";

const labels = {
  queued: "问题已保存，等待回答…",
  running: "AI 正在阅读并回答…",
  retrying: "暂时无法生成回答，将自动重试。",
  failed: "回答生成失败，问题和历史已保留。",
  success: "回答已保存，可以继续追问。",
};

export function NoteConversation({ noteId }: { noteId: number }) {
  const [open, setOpen] = useState(false);
  const user = useAccount();
  return (
    <section
      className="original-section note-conversation"
      aria-label="私人 AI 对话"
    >
      <div className="conversation-heading">
        <h2>与这篇笔记对话</h2>
        <button
          className="button secondary small"
          aria-expanded={open}
          aria-controls="note-conversation-panel"
          onClick={() => setOpen(!open)}
        >
          {open ? "收起对话" : "打开 AI 对话"}
        </button>
      </div>
      <p className="muted">围绕原文追问、梳理观点。对话仅自己可见。</p>
      {open && (
        <ConversationPanel
          key={`${user.id}:${noteId}`}
          noteId={noteId}
          userId={user.id}
        />
      )}
    </section>
  );
}

function ConversationPanel({
  noteId,
  userId,
}: {
  noteId: number;
  userId: number;
}) {
  const [history, setHistory] = useState<History | null>(null);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const [online, setOnline] = useState(true);
  const [busy, setBusy] = useState(false);
  const [olderBusy, setOlderBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const request = useRef<{ question: string; key: string } | null>(null);
  const lifetime = useRef<AbortController | null>(null);
  const sending = useRef(false);
  const list = useRef<HTMLOListElement>(null);
  const followAnswer = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight = false;
    async function refresh() {
      clearTimeout(timer);
      setOnline(navigator.onLine);
      if (
        inFlight ||
        !navigator.onLine ||
        document.visibilityState !== "visible"
      )
        return;
      inFlight = true;
      try {
        const result = await loadConversation(
          noteId,
          userId,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setHistory((previous) => ({
          ...result,
          turns: mergeMessages(previous?.turns ?? [], result.turns),
          next_before: previous ? previous.next_before : result.next_before,
        }));
        setError("");
        if (conversationPending(result.latest_job))
          timer = setTimeout(refresh, 2000);
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(errorMessage(cause));
          timer = setTimeout(refresh, 5000);
        }
      } finally {
        inFlight = false;
      }
    }
    const resume = () => {
      void refresh();
    };
    const offline = () => {
      setOnline(false);
      clearTimeout(timer);
    };
    void refresh();
    window.addEventListener("online", resume);
    window.addEventListener("offline", offline);
    window.addEventListener("focus", resume);
    document.addEventListener("visibilitychange", resume);
    return () => {
      controller.abort();
      clearTimeout(timer);
      window.removeEventListener("online", resume);
      window.removeEventListener("offline", offline);
      window.removeEventListener("focus", resume);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [noteId, userId, revision]);

  useEffect(() => {
    if (followAnswer.current && list.current) {
      list.current.scrollTop = list.current.scrollHeight;
      if (!conversationPending(history?.latest_job ?? null))
        followAnswer.current = false;
    }
  }, [history]);

  async function send(retry = false) {
    const signal = lifetime.current?.signal;
    if (
      !signal ||
      sending.current ||
      !navigator.onLine ||
      (!retry && !question.trim())
    )
      return;
    sending.current = true;
    setBusy(true);
    setError("");
    try {
      const value = question.trim();
      if (!retry && request.current?.question !== value)
        request.current = { question: value, key: captureKey() };
      const job =
        retry && history?.latest_job
          ? await retryQuestion(history.latest_job.id, userId, signal)
          : await askQuestion(
              noteId,
              userId,
              value,
              request.current!.key,
              signal,
            );
      if (signal.aborted) return;
      if (!retry) {
        setQuestion("");
        request.current = null;
      }
      setHistory((previous) =>
        previous ? { ...previous, latest_job: job } : previous,
      );
      followAnswer.current = true;
      setRevision((value) => value + 1);
    } catch (cause) {
      if (!signal.aborted) {
        setError(errorMessage(cause));
      }
    } finally {
      sending.current = false;
      if (!signal.aborted) setBusy(false);
    }
  }

  async function older() {
    const signal = lifetime.current?.signal;
    if (!signal || history?.next_before == null || olderBusy) return;
    setOlderBusy(true);
    try {
      const result = await loadConversation(
        noteId,
        userId,
        signal,
        history.next_before,
      );
      if (!signal.aborted)
        setHistory((previous) =>
          previous
            ? {
                ...previous,
                turns: mergeMessages(previous.turns, result.turns),
                next_before: result.next_before,
              }
            : result,
        );
    } catch (cause) {
      if (!signal.aborted) setError(errorMessage(cause));
    } finally {
      if (!signal.aborted) setOlderBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void send();
  }
  const job = history?.latest_job ?? null;
  const pending = conversationPending(job);
  const answers = new Set(
    history?.turns
      .filter((row) => row.role === "assistant")
      .map((row) => row.turn_index),
  );
  return (
    <div id="note-conversation-panel" className="conversation-panel">
      <p className="muted">
        提问会将正文和最近对话发送到你配置的模型服务，可能产生费用。AI
        回答请结合原文核对。
        <Link href="/settings/" className="text-link">
          模型设置
        </Link>
      </p>
      {!online && (
        <p className="notice" role="status">
          对话需要联网，连接恢复后可继续。
        </p>
      )}
      {!history && online && !error && <p role="status">正在加载对话…</p>}
      {history && history.turns.length === 0 && (
        <p className="conversation-empty">
          还没有对话。试着问：“这篇文章的主要论点是什么？”
        </p>
      )}
      {history?.next_before != null && (
        <button
          className="inline-button"
          onClick={older}
          disabled={olderBusy || !online}
        >
          {olderBusy ? "正在加载…" : "查看更早对话"}
        </button>
      )}
      <ol className="conversation-messages" aria-label="对话记录" ref={list}>
        {history?.turns.map((message) => (
          <ConversationMessage
            key={`${message.turn_index}:${message.role}`}
            message={message}
            unanswered={
              message.role === "user" &&
              !answers.has(message.turn_index) &&
              !(pending && message.turn_index === job?.turn_index)
            }
          />
        ))}
      </ol>
      {job && (
        <p role="status" aria-live="polite">
          {labels[job.status]}
          {job.last_error && ` ${job.last_error}`}
        </p>
      )}
      {job?.status === "failed" && (
        <button
          className="button secondary small"
          disabled={busy || !online}
          onClick={() => send(true)}
        >
          重试回答
        </button>
      )}
      {error && (
        <div className="notice error" role="alert">
          {error}{" "}
          <button
            className="inline-button"
            onClick={() => setRevision((value) => value + 1)}
          >
            刷新对话
          </button>
        </div>
      )}
      <form onSubmit={submit} className="conversation-form">
        <label htmlFor="conversation-question">向 AI 提问</label>
        <textarea
          id="conversation-question"
          rows={3}
          maxLength={4000}
          value={question}
          placeholder="围绕这篇文章提出问题…"
          disabled={busy}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <div className="conversation-submit">
          <small className="muted">
            {question.length} / 4000 · 最多参考最近 10 轮
          </small>
          <button
            className="button primary small"
            disabled={
              busy || pending || !online || !history || !question.trim()
            }
          >
            {busy ? "提交中…" : pending ? "等待回答…" : "发送问题"}
          </button>
        </div>
      </form>
    </div>
  );
}
