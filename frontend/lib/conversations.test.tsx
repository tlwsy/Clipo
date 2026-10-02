// SPDX-License-Identifier: AGPL-3.0-or-later
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationMessage } from "../components/conversation-message";
import { acceptSession } from "./api";
import {
  askQuestion,
  loadConversation,
  mergeMessages,
  retryQuestion,
  type Message,
} from "./conversations";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
const message: Message = {
  turn_index: 1,
  role: "user",
  content: "<script>alert(1)</script>",
  created_at: "2026-10-02T00:00:00Z",
};
function login() {
  acceptSession({
    access_token: "offline-chat",
    expires_in: 900,
    refresh_token: "unused",
    user: {
      id: 1,
      username: "demo",
      email: "demo@example.com",
      is_admin: true,
    },
  });
}
it("renders safe Markdown and rejects remote images, raw HTML and dangerous links", () => {
  const question = renderToStaticMarkup(
    createElement(ConversationMessage, { message, unanswered: true }),
  );
  expect(question).toContain("&lt;script&gt;");
  expect(question).toContain("这条问题尚无回答");
  const answer = renderToStaticMarkup(
    createElement(ConversationMessage, {
      message: {
        ...message,
        role: "assistant",
        content:
          "**重点**\n\n<script>alert(1)</script>\n\n![跟踪](https://example.com/pixel)\n\n[危险](javascript:alert%281%29) [来源](https://example.com)",
      },
    }),
  );
  expect(answer).toContain("<strong>重点</strong>");
  expect(answer).not.toMatch(/<script|<img|javascript:|href=""/);
  expect(answer).toContain('href="https://example.com"');
  expect(answer).toContain('rel="noreferrer noopener"');
});
it("merges polling and older pages without duplicate questions or out of order answers", () => {
  const answer = { ...message, role: "assistant" as const, content: "回答" };
  expect(mergeMessages([message], [answer, message])).toEqual([
    message,
    answer,
  ]);
  expect(
    mergeMessages([message, answer], [{ ...message, turn_index: 0 }]).map(
      (row) => row.turn_index,
    ),
  ).toEqual([0, 1, 1]);
});
it("preserves request keys and isolates every read, send and retry by account", async () => {
  login();
  const fetch = vi
    .fn()
    .mockImplementation(() => Promise.resolve(new Response("{}")));
  vi.stubGlobal("fetch", fetch);
  const signal = new AbortController().signal;
  await loadConversation(42, 1, signal, 7);
  await askQuestion(42, 1, "问题", "stable-key", signal);
  await askQuestion(42, 1, "问题", "stable-key", signal);
  await retryQuestion("job", 1, signal);
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/v1/notes/42/conversations?before=7",
  );
  expect(fetch.mock.calls[1][1].body).toBe(fetch.mock.calls[2][1].body);
  expect(fetch.mock.calls[3][0]).toBe("/api/v1/conversation-jobs/job/retry");
  expect(fetch.mock.calls[1][1].headers.get("Authorization")).toBe(
    "Bearer offline-chat",
  );
  await expect(askQuestion(42, 2, "问题", "key", signal)).rejects.toMatchObject(
    { code: "account_changed" },
  );
  expect(fetch).toHaveBeenCalledTimes(4);
});
it("times out uncertain requests and allows a fresh retry with the same key", async () => {
  login();
  vi.useFakeTimers();
  const fetch = vi
    .fn()
    .mockImplementation(
      (_path: string, options: RequestInit) =>
        new Promise((_resolve, reject) =>
          options.signal?.addEventListener("abort", () =>
            reject(new Error("aborted")),
          ),
        ),
    );
  vi.stubGlobal("fetch", fetch);
  const signal = new AbortController().signal;
  const result = expect(
    askQuestion(42, 1, "问题", "key", signal),
  ).rejects.toMatchObject({ code: "conversation_timeout" });
  await vi.advanceTimersByTimeAsync(15000);
  await result;
  fetch.mockResolvedValue(new Response("{}"));
  await askQuestion(42, 1, "问题", "key", signal);
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
  expect(signal.aborted).toBe(false);
});
it("aborts on leaving the reader without converting cancellation into a timeout", async () => {
  login();
  const fetch = vi
    .fn()
    .mockImplementation(
      (_path: string, options: RequestInit) =>
        new Promise((_resolve, reject) =>
          options.signal?.addEventListener("abort", () =>
            reject(new Error("left reader")),
          ),
        ),
    );
  vi.stubGlobal("fetch", fetch);
  const controller = new AbortController();
  const result = expect(
    loadConversation(42, 1, controller.signal),
  ).rejects.toThrow("left reader");
  controller.abort();
  await result;
});
