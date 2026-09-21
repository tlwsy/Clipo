import { api, ApiError, type Schema } from "./api";
import {
  applyOperations,
  enqueue,
  readAccount,
  readOffline,
  saveNotes,
} from "./offline-store";

let connected = true;
export function connectionAvailable(): boolean {
  return connected && (typeof navigator === "undefined" || navigator.onLine);
}
function connection(value: boolean): void {
  if (connected !== value) {
    connected = value;
    if (typeof window !== "undefined")
      window.dispatchEvent(new Event("clipo:connection"));
  }
}

export async function timedApi<T>(
  path: string,
  options: RequestInit & {
    expectedUserId?: number;
    authenticated?: boolean;
  } = {},
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;
  try {
    const value = await Promise.race<T>([
      api<T>(path, { ...options, signal: controller.signal }),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(new TypeError("连接超时"));
        }, 2000);
      }),
    ]);
    connection(true);
    return value;
  } catch (error) {
    if (unavailable(error)) connection(false);
    throw error;
  } finally {
    clearTimeout(timer!);
  }
}
function unavailable(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status >= 500;
}
export async function loadNote(id: number): Promise<Schema["NoteResponse"]> {
  const owner = await readAccount().catch(() => undefined);
  try {
    const note = await timedApi<Schema["NoteResponse"]>(`/notes/${id}`, {
      expectedUserId: owner?.user.id,
    });
    if (owner)
      await saveNotes(
        owner.generation,
        [note],
        undefined,
        owner.revision,
      ).catch(() => undefined);
    const local = await readOffline().catch(() => null);
    const visible = applyOperations([note], local?.operations ?? [])[0];
    if (!visible)
      throw new ApiError(404, "pending_deletion", "这篇笔记已加入删除队列");
    return visible;
  } catch (error) {
    if (!unavailable(error)) throw error;
    const local = await readOffline();
    const note = applyOperations(local.notes, local.operations).find(
      (note) => note.id === id,
    );
    if (!note)
      throw new ApiError(
        404,
        "offline_not_cached",
        "这篇笔记尚未缓存，请联网后打开",
      );
    return note;
  }
}
export async function loadNotes(path: string): Promise<Schema["NotePage"]> {
  try {
    const owner = await readAccount().catch(() => undefined);
    const page = await timedApi<Schema["NotePage"]>(path, {
      expectedUserId: owner?.user.id,
    });
    const local = await readOffline().catch(() => null);
    for (const operation of local?.operations ?? []) {
      const id = Number(operation.path.match(/^\/notes\/(\d+)$/)?.[1]);
      if (operation.method === "DELETE")
        page.items = page.items.filter((note) => note.id !== id);
      if (operation.method === "PATCH")
        page.items = page.items.map((note) =>
          note.id === id
            ? { ...note, is_favorite: JSON.parse(operation.body!).is_favorite }
            : note,
        );
    }
    return page;
  } catch (error) {
    if (!unavailable(error)) throw error;
    const local = await readOffline();
    const params = new URLSearchParams(path.split("?")[1]);
    if (params.has("cursor")) return { items: [], next_cursor: null };
    const terms = (params.get("q") ?? "")
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    const items = applyOperations(local.notes, local.operations)
      .filter(
        (note) =>
          !params.has("tag_id") ||
          note.tags.some((tag) => String(tag.id) === params.get("tag_id")),
      )
      .filter(
        (note) =>
          !params.has("favorite") ||
          String(note.is_favorite) === params.get("favorite"),
      )
      .filter((note) =>
        terms.every((term) =>
          [note.title, note.content.text, note.summary_markdown ?? ""]
            .join("\n")
            .toLowerCase()
            .includes(term),
        ),
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id)
      .map((note) => ({
        id: note.id,
        title: note.title,
        url: note.url,
        platform: note.source.platform,
        author: note.source.author,
        summary_excerpt: (
          note.summary_markdown ||
          note.content.text ||
          ""
        ).slice(0, 160),
        status: note.status,
        created_at: note.created_at,
        tags: note.tags,
        is_favorite: note.is_favorite,
      }));
    return { items, next_cursor: null };
  }
}
export async function loadTags(): Promise<Schema["TagResponse"][]> {
  try {
    return await timedApi<Schema["TagResponse"][]>("/tags");
  } catch (error) {
    if (!unavailable(error)) throw error;
    const local = await readOffline();
    return Array.from(
      new Map(
        local.notes.flatMap((note) => note.tags).map((tag) => [tag.id, tag]),
      ).values(),
    );
  }
}
export async function changeNote(
  id: number,
  method: "DELETE" | "PATCH",
  body?: { is_favorite: boolean },
): Promise<void> {
  const owner = await readAccount().catch(() => undefined);
  if (!owner) {
    await api(`/notes/${id}`, {
      method,
      body: body ? JSON.stringify(body) : undefined,
    });
    return;
  }
  // Persist before transmission: a closed tab or lost response can safely replay this operation.
  await enqueue({
    id: crypto.randomUUID(),
    owner: owner.generation,
    created: Date.now(),
    path: `/notes/${id}`,
    method,
    body: body ? JSON.stringify(body) : undefined,
  });
  const { syncOffline } = await import("./offline-sync");
  await syncOffline();
}

export async function saveCapture(url: string, key: string): Promise<void> {
  const owner = await readAccount().catch(() => undefined);
  const options = {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify({ url }),
  };
  try {
    await timedApi("/captures", { ...options, expectedUserId: owner?.user.id });
  } catch (error) {
    if (!owner || !unavailable(error)) throw error;
    await enqueue({
      id: key,
      owner: owner.generation,
      created: Date.now(),
      path: "/captures",
      method: "POST",
      body: options.body,
    });
  }
}
export async function localCaptures(): Promise<Schema["JobResponse"][]> {
  const local = await readOffline();
  return local.operations
    .filter((operation) => operation.path === "/captures")
    .map((operation) => ({
      job_id: "offline:" + operation.id,
      url: JSON.parse(operation.body!).url,
      status: "queued",
      attempts: 0,
      note_id: null,
      cached: false,
      next_retry_at: null,
      created_at: new Date(operation.created).toISOString(),
      updated_at: new Date(operation.created).toISOString(),
      last_error: operation.error ?? "保存在此设备，联网后提交。",
    }));
}
