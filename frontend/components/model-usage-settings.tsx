// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { useAccount } from "@/components/app-shell";
import { Icon } from "@/components/icon";
import { api, errorMessage, type Schema } from "@/lib/api";

export function ModelUsageSettings() {
  const user = useAccount();
  const [usage, setUsage] = useState<Schema["ModelUsageResponse"] | null>(null);
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const operation = useRef<AbortController | null>(null);
  const initialized = useRef(false);

  const refresh = useCallback(
    async (value?: string) => {
      const save = value !== undefined;
      operation.current?.abort();
      const controller = new AbortController();
      operation.current = controller;
      const timeout = setTimeout(() => controller.abort(), 15000);
      setBusy(true);
      setError("");
      setMessage("");
      try {
        const result = await api<Schema["ModelUsageResponse"]>(
          "/settings/model-usage",
          {
            expectedUserId: user.id,
            signal: controller.signal,
            ...(save
              ? {
                  method: "PUT",
                  body: JSON.stringify({
                    monthly_limit: value.trim() === "" ? null : Number(value),
                  } satisfies Schema["ModelUsageUpdate"]),
                }
              : {}),
          },
        );
        if (controller.signal.aborted) return;
        setUsage(result);
        if (save || !initialized.current) {
          setLimit(result.monthly_limit?.toString() ?? "");
          initialized.current = true;
        }
        if (save) setMessage("月度调用限额已保存，已用次数不会清零。");
      } catch (cause) {
        if (operation.current === controller)
          setError(
            controller.signal.aborted
              ? "请求超时，请刷新用量确认是否已保存。"
              : errorMessage(cause),
          );
      } finally {
        clearTimeout(timeout);
        if (operation.current === controller) setBusy(false);
      }
    },
    [user.id],
  );

  useEffect(() => {
    initialized.current = false;
    void refresh();
    return () => {
      operation.current?.abort();
      operation.current = null;
    };
  }, [refresh]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void refresh(limit);
  }

  return (
    <section
      className="settings-card"
      id="model-usage"
      aria-labelledby="model-usage-heading"
    >
      <div className="card-heading">
        <span className="feature-icon lavender">
          <Icon name="spark" />
        </span>
        <div>
          <h2 id="model-usage-heading">模型月度用量</h2>
          <p>为摘要、对话和语义搜索设置共同的调用上限</p>
        </div>
      </div>
      {usage && (
        <div aria-label="本月模型用量" aria-live="polite">
          <p>
            {usage.month}（UTC）· 已用 <strong>{usage.calls}</strong> 次 ·{" "}
            {usage.monthly_limit === null
              ? "当前不限"
              : `上限 ${usage.monthly_limit} 次 · 剩余 ${usage.remaining} 次`}
          </p>
          <p className="muted">
            下次重置：{new Date(usage.resets_at).toLocaleString("zh-CN")}
            （本地时间）
          </p>
          {usage.remaining === 0 && (
            <p className="notice">
              已达到本月上限，新的模型调用已暂停。调整限额或下月重置后，可重试失败的摘要、回答或索引任务。
            </p>
          )}
        </div>
      )}
      <form className="settings-form" onSubmit={submit}>
        <label>
          每月最多调用次数
          <input
            type="number"
            min={0}
            max={1000000}
            step={1}
            value={limit}
            disabled={busy || !usage}
            onChange={(event) => setLimit(event.target.value)}
            placeholder="不限"
          />
          <small>留空表示不限，0 表示暂停。按 UTC 自然月统计。</small>
        </label>
        <p className="section-description">
          每次模型请求计 1 次，失败和重试也计入；升级前的调用不计入。
          这是次数上限，金额预算仍需在模型服务商处设置。
          调整限额不撤销已开始的请求。
        </p>
        <div className="button-row">
          <button className="button" disabled={busy || !usage}>
            {busy ? "处理中…" : "保存月度限额"}
          </button>
          <button
            className="button secondary"
            type="button"
            disabled={busy}
            onClick={() => void refresh()}
          >
            刷新用量
          </button>
        </div>
      </form>
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
