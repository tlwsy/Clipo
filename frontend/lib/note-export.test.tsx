// SPDX-License-Identifier: AGPL-3.0-or-later
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ExportOptions } from "../components/export-options";
import { ExportMenu } from "../components/export-menu";
import { PdfExportDialog } from "../components/pdf-export-dialog";
import { acceptSession } from "./api";
import {
  defaultExportOptions,
  downloadExport,
  exportFilename,
  fetchNoteExport,
} from "./note-export";

const session = {
  access_token: "export-test-access",
  refresh_token: "unused",
  expires_in: 900,
  user: { id: 1, username: "demo", email: "demo@example.com", is_admin: true },
};
beforeEach(() => {
  acceptSession(session);
  vi.stubGlobal("navigator", { onLine: true });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("downloads authenticated UTF-8 text with all choices and cancellation signal", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("中文笔记😀"));
  vi.stubGlobal("fetch", fetch);
  const controller = new AbortController();
  const blob = await fetchNoteExport(
    42,
    "markdown",
    { ...defaultExportOptions, include_annotations: false },
    1,
    controller.signal,
  );
  expect(await blob.text()).toBe("中文笔记😀");
  const [path, options] = fetch.mock.calls[0];
  expect(path).toBe(
    "/api/v1/notes/42/export/markdown?include_summary=true&include_comments=true&include_annotations=false",
  );
  expect(options.headers.get("Authorization")).toBe(
    "Bearer export-test-access",
  );
  expect(options.signal).toBe(controller.signal);
  expect(options.cache).toBe("no-store");
});

it("renews expired sessions for exports and keeps structured download errors", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response("{}", { status: 401 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ ...session, access_token: "fresh" })),
    )
    .mockResolvedValueOnce(new Response("<html>阅读稿</html>"))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          error: { code: "note_not_found", message: "笔记已删除" },
        }),
        { status: 404 },
      ),
    );
  vi.stubGlobal("fetch", fetch);
  expect(
    await (await fetchNoteExport(42, "html", defaultExportOptions, 1)).text(),
  ).toContain("阅读稿");
  expect(fetch.mock.calls[2][1].headers.get("Authorization")).toBe(
    "Bearer fresh",
  );
  await expect(
    fetchNoteExport(42, "html", defaultExportOptions, 1),
  ).rejects.toMatchObject({ code: "note_not_found" });
});

it("rejects offline requests and account changes before sending any data", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  await expect(
    fetchNoteExport(42, "html", defaultExportOptions, 2),
  ).rejects.toMatchObject({ code: "account_changed" });
  vi.stubGlobal("navigator", { onLine: false });
  await expect(
    fetchNoteExport(42, "html", defaultExportOptions, 1),
  ).rejects.toMatchObject({ code: "offline_export" });
  expect(fetch).not.toHaveBeenCalled();
});

it("cleans filenames while preserving whole emoji and the correct extension", () => {
  expect(exportFilename('../中文/\\:*?"<>|\r\n\u202efile', 42, "html")).toBe(
    "中文file-42.html",
  );
  expect(exportFilename("...", 42, "markdown")).toBe("笔记-42.md");
  expect(exportFilename("😀".repeat(81), 42, "html")).toBe(
    `${"😀".repeat(80)}-42.html`,
  );
});

it("releases object URLs after starting a browser download", () => {
  vi.useFakeTimers();
  const link = { href: "", download: "", click: vi.fn(), remove: vi.fn() };
  const appendChild = vi.fn();
  vi.stubGlobal("document", {
    createElement: () => link,
    body: { appendChild },
  });
  const create = vi
    .spyOn(URL, "createObjectURL")
    .mockReturnValue("blob:export-test");
  const revoke = vi
    .spyOn(URL, "revokeObjectURL")
    .mockImplementation(() => undefined);
  const blob = new Blob(["正文"]);
  downloadExport(blob, "笔记-42.md");
  expect(create).toHaveBeenCalledWith(blob);
  expect(link.href).toBe("blob:export-test");
  expect(link.download).toBe("笔记-42.md");
  expect(link.click).toHaveBeenCalledOnce();
  expect(link.remove).toHaveBeenCalledOnce();
  expect(revoke).not.toHaveBeenCalled();
  vi.runAllTimers();
  expect(revoke).toHaveBeenCalledWith("blob:export-test");
});

it("offers explicit private-content choices and disables printing before preview is ready", () => {
  const options = renderToStaticMarkup(
    createElement(ExportOptions, {
      options: defaultExportOptions,
      onChange: () => undefined,
    }),
  );
  for (const value of ["包含 AI 摘要", "包含有价值评论", "包含私人标注"])
    expect(options).toContain(value);
  expect(options.match(/checked/g)).toHaveLength(3);
  const menu = renderToStaticMarkup(
    createElement(ExportMenu, { noteId: 42, title: "中文笔记" }),
  );
  expect(menu).toContain("导出笔记");
  const pdf = renderToStaticMarkup(
    createElement(PdfExportDialog, {
      noteId: 42,
      options: defaultExportOptions,
      onChange: () => undefined,
      onClose: () => undefined,
    }),
  );
  expect(pdf).toContain("PDF 打印预览");
  expect(pdf).toContain('disabled="">打印 / 保存为 PDF');
  expect(pdf).not.toContain("<iframe");
});
