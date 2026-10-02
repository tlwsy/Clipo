// SPDX-License-Identifier: AGPL-3.0-or-later
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryCard } from "../components/memory-card";
import { acceptSession } from "./api";
import {
  dismissMemory,
  loadMemories,
  memorySwipe,
  reportReading,
  trackReading,
  type MemoryNote,
} from "./memory";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const note: MemoryNote = {
  id: 42,
  title: "想法 <script>alert(1)</script>",
  url: "https://example.com/note",
  summary_snippet: "曾读过的观点",
  key_points: ["保留出处"],
  platform: "generic",
  site_name: "示例站点",
  created_at: "2026-01-01T00:00:00Z",
  annotations_count: 3,
  has_summary: true,
  is_favorite: false,
};

it("renders escaped content, source, reasons and a static reader URL", () => {
  const html = renderToStaticMarkup(createElement(MemoryCard, { note }));
  expect(html).toContain("&lt;script&gt;");
  expect(html).not.toContain("<script>");
  expect(html).toContain("示例站点");
  expect(html).toContain("3 处私人标注");
  expect(html).toContain("留有 AI 摘要");
  expect(html).toMatch(/href="\/notes\/?\?id=42"/);
  const read = renderToStaticMarkup(
    createElement(MemoryCard, {
      note: { ...note, annotations_count: 0, has_summary: false },
    }),
  );
  expect(read).toContain("曾认真读过");
});

it("distinguishes intentional horizontal swipes from taps and vertical scrolling", () => {
  expect(memorySwipe(-90, 12)).toBe("skip");
  expect(memorySwipe(90, -12)).toBe("favorite");
  expect(memorySwipe(20, 0)).toBeNull();
  expect(memorySwipe(90, 180)).toBeNull();
  expect(memorySwipe(-90, 90)).toBeNull();
});

it("uses shared authentication and expected account for requests including keepalive", async () => {
  acceptSession({
    access_token: "test-memory",
    expires_in: 900,
    refresh_token: "unused",
    user: {
      id: 1,
      username: "demo",
      email: "demo@example.com",
      is_admin: true,
    },
  });
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ notes: [note] })))
    .mockImplementation(() =>
      Promise.resolve(new Response(null, { status: 204 })),
    );
  vi.stubGlobal("fetch", fetch);
  expect(await loadMemories(1, new AbortController().signal)).toEqual([note]);
  await dismissMemory(42, 1);
  await reportReading(42, 1, 15);
  expect(fetch.mock.calls[2][0]).toBe("/api/v1/notes/42/view");
  expect(fetch.mock.calls[2][1].keepalive).toBe(true);
  expect(fetch.mock.calls[2][1].headers.get("Authorization")).toBe(
    "Bearer test-memory",
  );
  expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({
    duration_seconds: 15,
  });
  await expect(reportReading(42, 2, 15)).rejects.toMatchObject({
    code: "account_changed",
  });
  expect(fetch).toHaveBeenCalledTimes(3);
});

function environment() {
  vi.useFakeTimers();
  let now = 0;
  let focused = true;
  const page = Object.assign(new EventTarget(), {
    visibilityState: "visible",
    hasFocus: () => focused,
  });
  const browser = new EventTarget();
  const navigator = { onLine: true };
  vi.stubGlobal("window", browser);
  vi.stubGlobal("document", page);
  vi.stubGlobal("navigator", navigator);
  vi.stubGlobal("performance", { now: () => now });
  const elapse = (ms: number) => {
    now += ms;
  };
  const focus = (value: boolean) => {
    focused = value;
    browser.dispatchEvent(new Event(value ? "focus" : "blur"));
  };
  return { page, browser, navigator, elapse, focus };
}

it("records opens and visible focused time, then flushes once and removes listeners", () => {
  const env = environment();
  const report = vi.fn();
  const stop = trackReading(report);
  expect(report.mock.calls).toEqual([[0]]);
  env.elapse(5400);
  env.focus(false);
  expect(report.mock.calls).toEqual([[0], [5]]);
  env.elapse(120000);
  env.focus(true);
  env.elapse(600);
  stop();
  expect(report.mock.calls).toEqual([[0], [5], [1]]);
  env.browser.dispatchEvent(new Event("pagehide"));
  expect(report).toHaveBeenCalledTimes(3);
  expect(vi.getTimerCount()).toBe(0);
});

it("does not count background tabs, pagehide or offline periods and caps suspended time", () => {
  const env = environment();
  env.page.visibilityState = "hidden";
  const report = vi.fn();
  const stop = trackReading(report);
  env.elapse(60000);
  vi.advanceTimersByTime(15000);
  expect(report).not.toHaveBeenCalled();
  env.page.visibilityState = "visible";
  env.page.dispatchEvent(new Event("visibilitychange"));
  expect(report.mock.calls).toEqual([[0]]);
  env.elapse(2000);
  env.browser.dispatchEvent(new Event("pagehide"));
  env.elapse(60000);
  env.browser.dispatchEvent(new Event("pageshow"));
  expect(report.mock.calls).toEqual([[0], [2]]);
  env.navigator.onLine = false;
  env.browser.dispatchEvent(new Event("offline"));
  env.elapse(60000);
  env.navigator.onLine = true;
  env.browser.dispatchEvent(new Event("online"));
  env.elapse(3600000);
  vi.advanceTimersByTime(15000);
  expect(report.mock.calls).toEqual([[0], [2], [30]]);
  stop();
});
