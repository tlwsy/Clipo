// SPDX-License-Identifier: AGPL-3.0-or-later
import "fake-indexeddb/auto";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { acceptSession, type Schema } from "./api";
import { NoteCard } from "../components/note-card";
import { SearchHighlight } from "../components/search-highlight";
import { searchNotes, waitForSearch } from "./search";
import { loadNotes } from "./notes";
import { clearOffline, rememberAccount } from "./offline-store";

vi.mock("./notes", () => ({ loadNotes: vi.fn() }));
const note: Schema["SearchResult"] = {
  id: 1,
  title: "深度工作 <script>",
  url: "https://example.com",
  platform: "generic",
  author: null,
  summary_excerpt: "提升专注力",
  status: "ready",
  created_at: "2026-10-02T00:00:00Z",
  is_favorite: false,
  tags: [],
  score: 1,
  similarity: 0.8,
  match_type: "both",
};
beforeEach(async () => {
  await clearOffline();
  vi.stubGlobal("navigator", { onLine: true });
  acceptSession({
    access_token: "test-token",
    refresh_token: "unused",
    expires_in: 900,
    user: {
      id: 1,
      username: "demo",
      email: "demo@example.com",
      is_admin: true,
    },
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("renders match labels and safely highlights literal query words", () => {
  const html = renderToStaticMarkup(
    createElement(NoteCard, { note, searchQuery: "深度工作" }),
  );
  expect(html).toContain("语义与关键词匹配");
  expect(html).toContain('<mark class="search-highlight">深度工作</mark>');
  expect(html).toContain("&lt;script&gt;");
  expect(html).not.toContain("<script>");
  const semantic = renderToStaticMarkup(
    createElement(NoteCard, {
      note: { ...note, match_type: "semantic" },
      searchQuery: "深度工作",
    }),
  );
  expect(semantic).toContain("语义匹配");
  expect(semantic).not.toContain("<mark");
  const literal = renderToStaticMarkup(
    createElement(SearchHighlight, { text: "a+b c", query: "a+b" }),
  );
  expect(literal).toContain('<mark class="search-highlight">a+b</mark>');
});

it("uses the authenticated client, filters, and progressive backend status", async () => {
  const data = {
    results: [note],
    mode: "semantic",
    semantic_status: "queued",
    retry_after: 2,
  };
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(data)));
  vi.stubGlobal("fetch", fetch);
  const signal = new AbortController().signal;
  expect(
    await searchNotes("如何专注", { tag: "7", favorite: true }, 1, signal),
  ).toEqual(data);
  const [url, options] = fetch.mock.calls[0];
  const params = new URL(url, "https://clipo.example").searchParams;
  expect(params.get("q")).toBe("如何专注");
  expect(params.get("tag_id")).toBe("7");
  expect(params.get("favorite")).toBe("true");
  expect(options.headers.get("Authorization")).toBe("Bearer test-token");
});

it("falls back to existing keyword/offline search without claiming semantic matches", async () => {
  vi.stubGlobal("navigator", { onLine: false });
  vi.mocked(loadNotes).mockResolvedValue({ items: [note], next_cursor: null });
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const result = await searchNotes("专注", {}, 1, new AbortController().signal);
  expect(fetch).not.toHaveBeenCalled();
  expect(result.results[0].match_type).toBe("fulltext");
  expect(result.message).toContain("最近 50 篇缓存");
  expect(result.retry_after).toBeUndefined();
});

it("does not downgrade authentication/account errors or cancellations", async () => {
  const response = new Response(
    JSON.stringify({ error: { code: "rate_limited", message: "稍后重试" } }),
    { status: 429 },
  );
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  await expect(
    searchNotes("专注", {}, 1, new AbortController().signal),
  ).rejects.toMatchObject({ status: 429 });
  await expect(
    searchNotes("专注", {}, 2, new AbortController().signal),
  ).rejects.toMatchObject({ code: "account_changed" });
  vi.mocked(loadNotes).mockClear();
  const controller = new AbortController();
  controller.abort();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")),
  );
  await expect(
    searchNotes("专注", {}, 1, controller.signal),
  ).rejects.toMatchObject({ name: "AbortError" });
  expect(loadNotes).not.toHaveBeenCalled();
});

it("cancels pending polling delays immediately", async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  const pending = waitForSearch(2000, controller.signal);
  controller.abort();
  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  expect(vi.getTimerCount()).toBe(0);
});

it("rejects fallback data after the cached account changes", async () => {
  await rememberAccount({
    id: 2,
    username: "other",
    email: "other@example.com",
    is_admin: false,
  });
  vi.stubGlobal("navigator", { onLine: false });
  vi.mocked(loadNotes).mockClear();
  await expect(
    searchNotes("专注", {}, 1, new AbortController().signal),
  ).rejects.toMatchObject({ code: "account_changed" });
  expect(loadNotes).not.toHaveBeenCalled();
});
