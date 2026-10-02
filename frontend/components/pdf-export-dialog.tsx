// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useRef, useState } from "react";
import { errorMessage } from "@/lib/api";
import { readAccount } from "@/lib/offline-store";
import {
  fetchNoteExport,
  type ExportOptions as Options,
} from "@/lib/note-export";
import { CollectionDialog } from "./collection-dialog";
import { ExportOptions } from "./export-options";

export function PdfExportDialog({
  noteId,
  options,
  onChange,
  onClose,
}: {
  noteId: number;
  options: Options;
  onChange: (options: Options) => void;
  onClose: () => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; html: string } | null>(
    null,
  );
  const [readyKey, setReadyKey] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const optionsKey = JSON.stringify(options);
  const requestKey = `${noteId}:${optionsKey}:${attempt}`;
  const html = result?.key === requestKey ? result.html : "";
  const ready = !!html && readyKey === requestKey;

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    setMessage("");
    setReadyKey("");
    async function preview() {
      try {
        const owner = await readAccount().catch(() => undefined);
        if (controller.signal.aborted) return;
        const blob = await fetchNoteExport(
          noteId,
          "html",
          JSON.parse(optionsKey) as Options,
          owner?.user.id,
          controller.signal,
        );
        const value = await blob.text();
        if (!controller.signal.aborted)
          setResult({ key: requestKey, html: value });
      } catch (cause) {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      }
    }
    void preview();
    return () => controller.abort();
  }, [noteId, optionsKey, requestKey]);

  useEffect(() => {
    if (!html) return;
    // Remote images must not leave printing disabled indefinitely.
    const timer = setTimeout(() => {
      if (frame.current?.contentDocument?.querySelector("main")) {
        if (frame.current.contentDocument.readyState !== "complete") {
          frame.current.contentWindow?.stop();
          setMessage(
            "部分图片加载超时，已保留文字预览。可重新加载预览后再打印。",
          );
        }
        setReadyKey(requestKey);
      }
    }, 8000);
    return () => clearTimeout(timer);
  }, [html, requestKey]);

  function print() {
    if (!ready || !frame.current?.contentWindow) return;
    try {
      frame.current.contentWindow.focus();
      frame.current.contentWindow.print();
      setMessage(
        "已请求浏览器打印，请选择“另存为 PDF”。是否保存由打印窗口决定。",
      );
    } catch {
      setError("当前浏览器无法打开打印，请下载 HTML 文件后在浏览器中打印。");
    }
  }

  return (
    <CollectionDialog
      title="PDF 打印预览"
      onClose={onClose}
      className="pdf-export-dialog"
    >
      <div className="pdf-export-content">
        <ExportOptions options={options} onChange={onChange} />
        <p className="muted">
          预览会加载原网站图片。确认图片显示后打印，目标选择“另存为
          PDF”；建议关闭浏览器自带页眉页脚，使用文稿内的页码。
        </p>
        <div className="pdf-export-controls">
          <button
            className="button primary"
            disabled={!ready || !!error}
            onClick={print}
          >
            打印 / 保存为 PDF
          </button>
          <button className="button secondary" onClick={onClose}>
            取消
          </button>
          <button
            className="inline-button"
            onClick={() => setAttempt((value) => value + 1)}
          >
            重新加载预览
          </button>
        </div>
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        {!error && !ready && <p role="status">正在准备预览…</p>}
        {message && <p role="status">{message}</p>}
        {html && (
          <iframe
            key={requestKey}
            ref={frame}
            title="笔记打印预览"
            className="pdf-export-frame"
            sandbox="allow-same-origin allow-modals"
            referrerPolicy="no-referrer"
            srcDoc={html}
            onLoad={() => setReadyKey(requestKey)}
          />
        )}
      </div>
    </CollectionDialog>
  );
}
