import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CHUNK_BYTES,
  ApiError,
  request,
  serverAddress,
  submit,
} from "../lib/api.mjs";
import "../../frontend/node_modules/fake-indexeddb/auto/index.mjs";
import * as queue from "../lib/store.mjs";

test("server origin accepts private development and rejects unsafe destinations", () => {
  assert.equal(
    serverAddress("https://clipo.example.com/"),
    "https://clipo.example.com",
  );
  assert.equal(
    serverAddress("http://192.168.137.1:18000"),
    "http://192.168.137.1:18000",
  );
  for (const url of [
    "javascript:alert(1)",
    "https://user:pass@example.com",
    "http://example.com",
    "https://example.com/api",
    "https://example.com/?token=secret",
  ])
    assert.throws(() => serverAddress(url));
});
test("authenticated requests omit cookies, reject redirects, and hide upstream secrets", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (...args) => {
    calls.push(args);
    return new Response('{"secret":"ct_private"}', { status: 401 });
  };
  try {
    await assert.rejects(
      request(
        { server: "https://clipo.example.com", token: "ct_test" },
        "/auth/me",
      ),
      (error) =>
        error instanceof ApiError && !error.message.includes("private"),
    );
    assert.equal(calls[0][1].credentials, "omit");
    assert.equal(calls[0][1].redirect, "error");
    assert.equal(calls[0][1].headers["X-Clipo-Token"], "ct_test");
  } finally {
    globalThis.fetch = original;
  }
});
test("direct submit preserves payload, key and selection", async () => {
  const payload = { title: "网页", text: "正文", selection: "选区" };
  const item = {
    id: "once",
    url: "https://example.com",
    bytes: new TextEncoder().encode(JSON.stringify(payload)),
  };
  const job = await submit(
    {},
    item,
    () => {},
    async (config, path, options) => {
      assert.equal(path, "/captures");
      assert.equal(options.key, "once");
      assert.deepEqual(options.json.payload, payload);
      return { job_id: "j_1" };
    },
  );
  assert.equal(job.job_id, "j_1");
});
test("large UTF-8 payload resumes persisted chunks after an interrupted acknowledgement", async () => {
  const item = {
    id: "large",
    configId: "account",
    url: "https://example.com",
    bytes: new TextEncoder().encode(
      JSON.stringify({ title: "大正文", text: "中文".repeat(950000) }),
    ),
  };
  await queue.save(item);
  const chunks = new Map();
  let interrupted = false;
  const call = async (config, path, options) => {
    if (path === "/captures/uploads")
      return { job_id: "j_large", status: "uploading" };
    if (path.endsWith("/complete"))
      return { job_id: "j_large", status: "queued" };
    const index = Number(path.split("/").at(-1));
    if (chunks.has(index)) assert.deepEqual(options.bytes, chunks.get(index));
    chunks.set(index, options.bytes);
    if (index === 2 && !interrupted) {
      interrupted = true;
      throw new Error("connection lost");
    }
  };
  await assert.rejects(submit({}, item, queue.save, call));
  const [restored] = await queue.pending();
  assert.equal(restored.nextChunk, 2);
  assert.equal((await submit({}, restored, queue.save, call)).status, "queued");
  assert.equal(chunks.size, Math.ceil(item.bytes.length / CHUNK_BYTES));
  assert.deepEqual(
    Buffer.concat([...chunks.values()]),
    Buffer.from(item.bytes),
  );
  await queue.clear();
  assert.equal((await queue.pending()).length, 0);
});

test("recovered creation acknowledgement for an accepted upload never checkpoints a closed session", async () => {
  const item = {
    id: "already-accepted",
    url: "https://example.com",
    bytes: new TextEncoder().encode(
      JSON.stringify({ title: "Large", text: "a".repeat(6 * 1024 * 1024) }),
    ),
  };
  const result = await submit(
    {},
    item,
    () => {
      throw new Error("must not checkpoint closed upload");
    },
    async (config, path) => {
      assert.equal(path, "/captures/uploads");
      return { job_id: "j_done", status: "success" };
    },
  );
  assert.equal(result.status, "success");
});
