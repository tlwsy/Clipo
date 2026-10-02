// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, errorMessage, type Schema } from "@/lib/api";
import { useAccount } from "@/components/app-shell";
import { Icon } from "@/components/icon";

export function SemanticSettings({
  initial,
}: {
  initial: Schema["LlmResponse"];
}) {
  const user = useAccount();
  const [enabled, setEnabled] = useState(initial.embedding_enabled ?? false);
  const [model, setModel] = useState(
    initial.embedding_model ?? "text-embedding-3-small",
  );
  const [status, setStatus] = useState<Schema["EmbeddingIndexResponse"] | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const operation = useRef<AbortController | null>(null);
  useEffect(() => () => operation.current?.abort(), []);
  useEffect(() => {
    const refresh = () => setRevision((value) => value + 1);
    window.addEventListener("clipo:model-settings", refresh);
    return () => window.removeEventListener("clipo:model-settings", refresh);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const started = Date.now();
    async function refresh() {
      try {
        const result = await api<Schema["EmbeddingIndexResponse"]>(
          "/settings/search-index",
          {
            signal: controller.signal,
            expectedUserId: user.id,
          },
        );
        if (controller.signal.aborted) return;
        setStatus(result);
        if (
          (result.pending || result.backfill_running) &&
          Date.now() - started < 120000
        )
          timer = setTimeout(refresh, 3000);
      } catch (cause) {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [revision, user.id]);

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const controller = new AbortController();
    operation.current?.abort();
    operation.current = controller;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (event) {
        const result = await api<Schema["SettingsResponse"]>("/settings", {
          method: "PUT",
          signal: controller.signal,
          expectedUserId: user.id,
          body: JSON.stringify({
            llm: { embedding_enabled: enabled, embedding_model: model },
          } satisfies Schema["SettingsUpdate"]),
        });
        if (controller.signal.aborted) return;
        setEnabled(result.llm.embedding_enabled ?? false);
        setModel(result.llm.embedding_model ?? "text-embedding-3-small");
        setMessage(
          result.llm.embedding_enabled
            ? "语义搜索设置已保存，后台将自动补齐索引。"
            : "语义搜索已关闭，关键词搜索仍可用。",
        );
      } else {
        await api("/settings/search-index", {
          method: "POST",
          signal: controller.signal,
          expectedUserId: user.id,
        });
        if (controller.signal.aborted) return;
        setMessage("已提交补齐和失败重试请求，有效向量不会重复生成。");
      }
      setRevision((value) => value + 1);
    } catch (cause) {
      if (!controller.signal.aborted) setError(errorMessage(cause));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="settings-card" id="semantic-search">
      <div className="card-heading">
        <span className="feature-icon">
          <Icon name="spark" />
        </span>
        <div>
          <h2>AI 语义搜索</h2>
          <p>描述想找的内容，找回相关笔记</p>
        </div>
      </div>
      <form className="settings-form" onSubmit={submit}>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          开启语义搜索
        </label>
        <label>
          嵌入模型名称
          <input
            required
            maxLength={100}
            value={model}
            onChange={(event) => setModel(event.target.value)}
          />
          <small>
            复用上方 AI 模型的服务地址和密钥；服务需支持 1536
            维嵌入接口，聊天模型通常不能直接用于嵌入。
          </small>
        </label>
        <p className="notice">
          开启后会将已有及新笔记的标题、摘要、要点和搜索问题发送到所配置的模型服务，产生额外调用费用。私人批注和评论不参与向量生成。
        </p>
        <button className="button" disabled={busy}>
          {busy ? "处理中…" : "保存语义搜索设置"}
        </button>
      </form>
      {status && (
        <div className="semantic-index-status" aria-label="语义索引状态">
          <p>
            已建立索引 <strong>{status.ready}</strong> / {status.total} 篇 ·
            待处理 {status.pending} 篇 · 异常或重试 {status.failed} 篇
          </p>
          <p className="muted">
            {status.backfill_running
              ? "正在扫描并补齐已有笔记。"
              : "后台任务由 worker 处理。"}
            {status.backend === "sqlite_exact"
              ? " 本地 SQLite 使用精确检索，适合小型资料库。"
              : " PostgreSQL 向量索引已接入。"}
          </p>
          <div className="button-row">
            <button
              className="button secondary small"
              disabled={busy || !status.enabled || !status.configured}
              onClick={() => void submit()}
            >
              补齐索引 / 重试失败
            </button>
            <button
              className="inline-button"
              disabled={busy}
              onClick={() => {
                setError("");
                setRevision((value) => value + 1);
              }}
            >
              刷新索引状态
            </button>
          </div>
          {!status.configured && (
            <p className="muted">请先在上方 AI 模型中保存可用的 API Key。</p>
          )}
        </div>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="notice success" role="status">
          {message}
        </p>
      )}
    </section>
  );
}
