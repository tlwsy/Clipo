import "fake-indexeddb/auto";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import {
  clearOffline,
  rememberAccount,
  readAccount,
  readOffline,
  saveNotes,
  enqueue,
  completeOperation,
  discardOperation,
  applyOperations,
  type Operation,
} from "./offline-store";
import { acceptSession, type Schema } from "./api";
import { loadNotes, loadNote, saveCapture } from "./notes";
import { syncOffline } from "./offline-sync";

const user = {
  id: 1,
  username: "admin",
  email: "admin@example.com",
  is_admin: true,
};
function note(id: number): Schema["NoteResponse"] {
  return {
    id,
    title: `中文笔记 ${id}`,
    url: "https://example.com/article",
    source: {
      platform: "web",
      origin_url: "https://example.com/article",
      author: null,
      author_url: null,
      published_at: null,
    },
    content: {
      url: "https://example.com/article",
      title: "中文笔记",
      text: "原始正文",
      platform: "web",
      extractor_version: 1,
    },
    comments: [],
    summary_markdown: "摘要",
    key_points: [],
    suggested_tags: [],
    tags: [{ id: 1, name: "知识" }],
    status: "ready",
    is_favorite: false,
    summary_error: null,
    comment_score_error: null,
    created_at: new Date(id * 1000).toISOString(),
    updated_at: new Date(id * 1000).toISOString(),
  };
}
function response(data: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(data), { status });
}
let owner: Awaited<ReturnType<typeof rememberAccount>>;
beforeEach(async () => {
  vi.stubGlobal("navigator", { onLine: true });
  vi.stubGlobal("window", new EventTarget());
  vi.stubGlobal("localStorage", { setItem: vi.fn() });
  await clearOffline();
  owner = await rememberAccount(user);
  acceptSession({
    user,
    access_token: "test-token",
    refresh_token: "not-persisted",
    expires_in: 900,
  });
});
afterEach(() => vi.unstubAllGlobals());
function deletion(id = 1): Operation {
  return {
    id: crypto.randomUUID(),
    owner: owner.generation,
    created: Date.now(),
    path: `/notes/${id}`,
    method: "DELETE",
  };
}

describe("account-scoped offline notes", () => {
  it("retains only 50 most recent notes and ignores stale writes after switching accounts", async () => {
    await saveNotes(
      owner.generation,
      Array.from({ length: 55 }, (_, i) => note(i + 1)),
    );
    const local = await readOffline();
    expect(local.notes).toHaveLength(50);
    expect(local.notes.some((item) => item.id === 1)).toBe(false);
    await enqueue(deletion());
    await rememberAccount({ ...user, id: 2, username: "other" });
    await saveNotes(owner.generation, [note(100)]);
    expect((await readOffline()).notes).toEqual([]);
    expect((await readOffline()).operations).toEqual([]);
    await expect(enqueue(deletion())).rejects.toThrow("账号已切换");
  });
  it("does not resurrect a deleted note when an older prefetch finishes", async () => {
    await saveNotes(owner.generation, [note(1)], undefined, owner.revision);
    const operation = deletion();
    await enqueue(operation);
    await completeOperation(operation);
    await saveNotes(owner.generation, [note(1)], [1], owner.revision);
    expect((await readOffline()).notes).toEqual([]);
  });
  it("supports offline full text, tag and favorite filters, and queued deletion across reads", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await saveNotes(owner.generation, [note(1), note(2)]);
    await enqueue({
      ...deletion(),
      method: "PATCH",
      body: JSON.stringify({ is_favorite: true }),
    });
    expect(
      (await loadNotes("/notes?q=中文 摘要&tag_id=1&favorite=true")).items.map(
        (item) => item.id,
      ),
    ).toEqual([1]);
    expect((await loadNote(1)).is_favorite).toBe(true);
    await enqueue(deletion());
    expect((await loadNotes("/notes")).items.map((item) => item.id)).toEqual([
      2,
    ]);
    await expect(loadNote(1)).rejects.toMatchObject({
      code: "offline_not_cached",
    });
  });
  it("keeps insertion order for writes with equal clock timestamps", async () => {
    await enqueue({
      ...deletion(),
      id: "z",
      created: 1,
      method: "PATCH",
      body: '{"is_favorite":true}',
    });
    await enqueue({
      ...deletion(),
      id: "a",
      created: 1,
      method: "PATCH",
      body: '{"is_favorite":false}',
    });
    const local = await readOffline();
    expect(local.operations.map((operation) => operation.id)).toEqual([
      "z",
      "a",
    ]);
    expect(applyOperations([note(1)], local.operations)[0].is_favorite).toBe(
      false,
    );
  });
  it("clears notes, account and pending operations together on logout", async () => {
    await saveNotes(owner.generation, [note(1)]);
    await enqueue(deletion());
    await clearOffline();
    expect(await readAccount()).toBeUndefined();
    expect((await readOffline()).notes).toEqual([]);
    expect((await readOffline()).operations).toEqual([]);
  });
  it("allows cancelling a failed deletion without removing the original cached note", async () => {
    await saveNotes(owner.generation, [note(1)]);
    const operation = { ...deletion(), error: "暂时无法删除" };
    await enqueue(operation);
    await discardOperation(operation);
    const local = await readOffline();
    expect(local.notes[0].id).toBe(1);
    expect(local.operations).toEqual([]);
  });
  it("does not use cached private notes when the server rejects authentication", async () => {
    await saveNotes(owner.generation, [note(1)]);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response(
            { error: { code: "authentication_required", message: "请先登录" } },
            401,
          ),
        ),
    );
    await expect(loadNote(1)).rejects.toMatchObject({ status: 401 });
  });
});
describe("durable offline replay", () => {
  it("retains failed writes then treats an already deleted note as successful", async () => {
    const operation = deletion();
    await saveNotes(owner.generation, [note(1)]);
    await enqueue(operation);
    const fetch = vi
      .fn()
      .mockImplementation(async (path: string) =>
        path.endsWith("/auth/me")
          ? response(user)
          : response({ error: { message: "服务暂不可用" } }, 503),
      );
    vi.stubGlobal("fetch", fetch);
    await syncOffline();
    expect((await readOffline()).operations[0].error).toBe("服务暂不可用");
    fetch.mockImplementation(async (path: string) =>
      path.endsWith("/auth/me") ? response(user) : response({}, 404),
    );
    await Promise.all([syncOffline(), syncOffline()]);
    expect((await readOffline()).operations).toEqual([]);
    expect((await readOffline()).notes).toEqual([]);
    expect(
      fetch.mock.calls.filter(([path]) => path.endsWith("/notes/1")),
    ).toHaveLength(2);
  });
  it("retries when reconnection arrives during a failing sync attempt", async () => {
    await enqueue(deletion());
    let fail!: (error: Error) => void;
    let started!: () => void;
    const beginning = new Promise<void>((resolve) => {
      started = resolve;
    });
    const fetch = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((_, reject) => {
            fail = reject;
            started();
          }),
      )
      .mockImplementation(async (path: string) =>
        path.endsWith("/auth/me") ? response(user) : response(null, 204),
      );
    vi.stubGlobal("fetch", fetch);
    const first = syncOffline();
    await beginning;
    const second = syncOffline();
    fail(new TypeError("previous offline request"));
    await Promise.all([first, second]);
    expect((await readOffline()).operations).toEqual([]);
  });
  it("refuses to replay or cache private data under a different live account", async () => {
    await enqueue(deletion());
    const fetch = vi.fn().mockResolvedValue(response({ ...user, id: 2 }));
    vi.stubGlobal("fetch", fetch);
    await syncOffline();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect((await readOffline()).operations).toHaveLength(1);
    acceptSession({
      user: { ...user, id: 2 },
      access_token: "other",
      refresh_token: "not-stored",
      expires_in: 900,
    });
    await expect(loadNote(1)).rejects.toMatchObject({
      code: "account_changed",
    });
  });
  it("replays an uncertain capture response using the original idempotency key", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("lost response")),
    );
    await saveCapture("https://example.com/article", "capture-unique-key");
    expect((await readOffline()).operations[0].id).toBe("capture-unique-key");
    const fetch = vi
      .fn()
      .mockImplementation(async (path: string) =>
        path.endsWith("/auth/me") ? response(user) : response({}, 202),
      );
    vi.stubGlobal("fetch", fetch);
    await syncOffline();
    expect(fetch.mock.calls[1][1].headers.get("Idempotency-Key")).toBe(
      "capture-unique-key",
    );
    expect((await readOffline()).operations).toEqual([]);
  });
  it("preserves favorite ordering and deletion without mutating stored originals", () => {
    const original = note(1);
    const ops = [
      { ...deletion(), method: "PATCH" as const, body: '{"is_favorite":true}' },
    ];
    expect(applyOperations([original], ops)[0].is_favorite).toBe(true);
    expect(original.is_favorite).toBe(false);
    expect(applyOperations([original], [...ops, deletion()])).toEqual([]);
  });
});

describe("HTTP hotspot compatibility", () => {
  it("retains account isolation and can log out without secure-context randomUUID", async () => {
    const getRandomValues = crypto.getRandomValues.bind(crypto);
    vi.stubGlobal("crypto", { getRandomValues });
    await clearOffline();
    const account = await rememberAccount(user);
    expect(account.generation).toHaveLength(32);
    const other = await rememberAccount({ ...user, id: 2, username: "second" });
    expect(other.generation).not.toBe(account.generation);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(null, 204)));
    const { logout } = await import("./api");
    await expect(logout()).resolves.toBeUndefined();
    expect(await readAccount()).toBeUndefined();
  });
});
