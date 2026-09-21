"use client";

import { useState, type FormEvent } from "react";

import { Icon } from "@/components/icon";
import { api, errorMessage, type Schema } from "@/lib/api";

export function CaptureSettings({
  initial,
}: {
  initial: Schema["CaptureSettingsResponse"];
}) {
  const [maxComments, setMaxComments] = useState(String(initial.max_comments));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const result = await api<Schema["SettingsResponse"]>("/settings", {
        method: "PUT",
        body: JSON.stringify({
          capture: { max_comments: Number(maxComments) },
        } satisfies Schema["SettingsUpdate"]),
      });
      setMaxComments(String(result.capture.max_comments));
      setMessage("采集配置已保存，将在后续任务执行时生效");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="settings-card" id="capture">
      <div className="card-heading">
        <span className="feature-icon">
          <Icon name="bookmark" />
        </span>
        <div>
          <h2>内容采集</h2>
          <p>选择每篇笔记保留多少评论</p>
        </div>
      </div>
      <form onSubmit={save}>
        <label>
          评论采集上限
          <input
            type="number"
            required
            min={0}
            max={100}
            step={1}
            value={maxComments}
            disabled={busy}
            onChange={(event) => setMaxComments(event.target.value)}
          />
          <small>
            默认 100 条，设为 0
            可关闭评论采集。当前适用于小红书，保留已有的顶层评论并尝试补抓分页，实际条数可能更少。
          </small>
        </label>
        <p className="section-description">
          AI
          只会从已采集的评论中选择候选评分，可在模型设置中另设候选上限。修改不影响已有笔记；小红书分页需要完整
          Cookie 和带访问参数的帖子链接。
        </p>
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        {message && (
          <div className="notice success" role="status">
            {message}
          </div>
        )}
        <div className="form-bottom">
          <span>
            <Icon name="lock" size={14} /> 仅供当前账号使用
          </span>
          <button className="button" disabled={busy}>
            {busy ? "保存中…" : "保存采集配置"}
          </button>
        </div>
      </form>
    </section>
  );
}
