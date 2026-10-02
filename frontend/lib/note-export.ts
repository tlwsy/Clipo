// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, ApiError } from "./api";
import type { operations } from "./api-types";

export type ExportOptions = Required<
  NonNullable<
    operations["export_html_api_v1_notes__note_id__export_html_get"]["parameters"]["query"]
  >
>;
export type ExportFormat = "markdown" | "html";
export const defaultExportOptions: ExportOptions = {
  include_summary: true,
  include_comments: true,
  include_annotations: true,
};

export function fetchNoteExport(
  noteId: number,
  format: ExportFormat,
  options: ExportOptions,
  expectedUserId?: number,
  signal?: AbortSignal,
): Promise<Blob> {
  if (typeof navigator !== "undefined" && !navigator.onLine)
    return Promise.reject(
      new ApiError(0, "offline_export", "导出需要联网，请连接服务后重试。"),
    );
  const params = new URLSearchParams(
    Object.entries(options).map(([key, value]) => [key, String(value)]),
  );
  return api(`/notes/${noteId}/export/${format}?${params}`, {
    responseType: "blob",
    expectedUserId,
    signal,
  });
}

export function exportFilename(
  title: string,
  noteId: number,
  format: ExportFormat,
): string {
  const cleaned =
    Array.from(title.replace(/[\p{C}/\\:*?"<>|]/gu, "").replace(/\s+/g, " "))
      .slice(0, 80)
      .join("")
      .replace(/^[ .]+|[ .]+$/g, "") || "笔记";
  return `${cleaned}-${noteId}.${format === "markdown" ? "md" : "html"}`;
}

export function downloadExport(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  try {
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    // Keep the URL alive until the browser has started consuming the download.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
