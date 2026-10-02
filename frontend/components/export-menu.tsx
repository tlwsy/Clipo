// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useRef, useState } from "react";
import { errorMessage } from "@/lib/api";
import { readAccount } from "@/lib/offline-store";
import {
  defaultExportOptions,
  downloadExport,
  exportFilename,
  fetchNoteExport,
  type ExportFormat,
} from "@/lib/note-export";
import { CollectionDialog } from "./collection-dialog";
import { ExportOptions } from "./export-options";
import { PdfExportDialog } from "./pdf-export-dialog";
import { Icon } from "./icon";

export function ExportMenu({
  noteId,
  title,
}: {
  noteId: number;
  title: string;
}) {
  const [mode, setMode] = useState<"menu" | "pdf" | null>(null);
  const [options, setOptions] = useState(defaultExportOptions);
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  function close() {
    request.current?.abort();
    setMode(null);
    setBusy(null);
  }
  async function download(format: ExportFormat) {
    if (busy) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(format);
    setError("");
    setMessage("");
    try {
      const owner = await readAccount().catch(() => undefined);
      if (controller.signal.aborted) return;
      const blob = await fetchNoteExport(
        noteId,
        format,
        options,
        owner?.user.id,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      downloadExport(blob, exportFilename(title, noteId, format));
      setMessage("已发起下载，请在浏览器下载列表中查看。");
    } catch (cause) {
      if (!controller.signal.aborted) setError(errorMessage(cause));
    } finally {
      if (!controller.signal.aborted) setBusy(null);
    }
  }
  return (
    <>
      <button
        className="button secondary small"
        onClick={() => {
          setError("");
          setMessage("");
          setMode("menu");
        }}
      >
        <Icon name="download" size={16} />
        导出笔记
      </button>
      {mode === "menu" && (
        <CollectionDialog
          title="导出笔记"
          onClose={close}
          className="export-menu-dialog"
        >
          <p>保存这篇笔记的阅读稿，选择需要包含的内容。</p>
          <ExportOptions
            options={options}
            onChange={setOptions}
            disabled={busy !== null}
          />
          <p className="muted">
            私人标注包含高亮和完整批注。发送给他人前，请核对导出选项。
          </p>
          <div className="export-actions">
            <button
              className="button secondary"
              disabled={busy !== null}
              onClick={() => download("markdown")}
            >
              {busy === "markdown" ? "正在导出…" : "导出为 Markdown"}
            </button>
            <button
              className="button secondary"
              disabled={busy !== null}
              onClick={() => download("html")}
            >
              {busy === "html" ? "正在导出…" : "导出为 HTML"}
            </button>
            <button
              className="button primary"
              disabled={busy !== null}
              onClick={() => setMode("pdf")}
            >
              导出为 PDF
            </button>
          </div>
          <p className="muted">
            PDF
            使用浏览器打印。图片为原网站引用，离线或防盗链可能导致图片不可用。
          </p>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          {message && <p role="status">{message}</p>}
        </CollectionDialog>
      )}
      {mode === "pdf" && (
        <PdfExportDialog
          noteId={noteId}
          options={options}
          onChange={setOptions}
          onClose={close}
        />
      )}
    </>
  );
}
