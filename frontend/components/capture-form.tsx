"use client";
import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, type Schema } from "@/lib/api";
import { Icon } from "./icon";
import { captureKey } from "@/lib/share";

export function CaptureForm() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef({ url: "", key: "" });
  const router = useRouter();
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    if (request.current.url !== url)
      request.current = { url, key: captureKey() };
    try {
      await api<Schema["JobResponse"]>("/captures", {
        method: "POST",
        headers: { "Idempotency-Key": request.current.key },
        body: JSON.stringify({ url } satisfies Schema["CaptureRequest"]),
      });
      router.push("/jobs/");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="capture-card">
      <span className="feature-icon">
        <Icon name="clip" />
      </span>
      <div className="capture-copy">
        <h2>把好内容留在这里</h2>
        <p>粘贴网页链接，自动提取正文。配置 AI 后，还会为你整理摘要与要点。</p>
        <form className="capture-form" onSubmit={save}>
          <label>
            <span className="sr-only">网页链接</span>
            <input
              type="url"
              required
              maxLength={4096}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://… 粘贴文章链接"
              disabled={busy}
            />
          </label>
          <button className="button" disabled={busy || !url.trim()}>
            {busy ? "提交中…" : "保存网页"}
            <Icon name="arrow" size={16} />
          </button>
        </form>
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
      </div>
    </section>
  );
}
