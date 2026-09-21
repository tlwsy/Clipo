import type { Schema } from "./api";

type Account = {
  user: Schema["UserResponse"];
  generation: string;
  revision: number;
};
export type Operation = {
  id: string;
  owner: string;
  created: number;
  path: string;
  method: "DELETE" | "PATCH" | "POST";
  body?: string;
  error?: string;
};
type StoredNote = { owner: string; id: number; note: Schema["NoteResponse"] };
let database: Promise<IDBDatabase> | undefined;

function open(): Promise<IDBDatabase> {
  if (!database) {
    database = new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("clipo-offline", 1);
      request.onupgradeneeded = () => {
        request.result.createObjectStore("meta");
        request.result.createObjectStore("notes", { keyPath: ["owner", "id"] });
        request.result.createObjectStore("operations", { keyPath: "id" });
      };
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        request.result.onversionchange = () => {
          request.result.close();
          database = undefined;
        };
        resolve(request.result);
      };
    }).catch((error) => {
      database = undefined;
      throw error;
    });
  }
  return database;
}
function result<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function transaction<T>(
  mode: IDBTransactionMode,
  run: (tx: IDBTransaction) => Promise<T>,
): Promise<T> {
  const db = await open();
  const tx = db.transaction(["meta", "notes", "operations"], mode);
  const done = new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onabort = () => reject(tx.error ?? new Error("离线存储未完成"));
    tx.onerror = () => reject(tx.error);
  });
  try {
    const value = await run(tx);
    await done;
    return value;
  } catch (error) {
    try {
      tx.abort();
    } catch {}
    await done.catch(() => undefined);
    throw error;
  }
}
function account(tx: IDBTransaction): Promise<Account | undefined> {
  return result(tx.objectStore("meta").get("account"));
}
function changed(): void {
  if (typeof window !== "undefined")
    window.dispatchEvent(new Event("clipo:offline-changed"));
}
export async function readAccount(): Promise<Account | undefined> {
  return transaction("readonly", account);
}
export async function rememberAccount(
  user: Schema["UserResponse"],
): Promise<Account> {
  return transaction("readwrite", async (tx) => {
    const previous = await account(tx);
    if (
      previous?.user.id === user.id &&
      previous.user.username === user.username &&
      previous.user.email === user.email
    ) {
      const updated = { ...previous, user };
      tx.objectStore("meta").put(updated, "account");
      return updated;
    }
    if (typeof window !== "undefined")
      localStorage.setItem("clipo:session", crypto.randomUUID());
    tx.objectStore("notes").clear();
    tx.objectStore("operations").clear();
    tx.objectStore("meta").clear();
    const next = { user, generation: crypto.randomUUID(), revision: 0 };
    tx.objectStore("meta").put(next, "account");
    return next;
  });
}
export async function clearOffline(): Promise<void> {
  await transaction("readwrite", async (tx) => {
    for (const name of ["meta", "notes", "operations"])
      tx.objectStore(name).clear();
  });
  changed();
}
export async function readOffline(): Promise<{
  account?: Account;
  notes: Schema["NoteResponse"][];
  operations: Operation[];
}> {
  return transaction("readonly", async (tx) => {
    const owner = await account(tx);
    const rows: StoredNote[] = await result(tx.objectStore("notes").getAll());
    const operations: Operation[] = await result(
      tx.objectStore("operations").getAll(),
    );
    return {
      account: owner,
      notes: rows
        .filter((row) => row.owner === owner?.generation)
        .map((row) => row.note),
      operations: operations
        .filter((row) => row.owner === owner?.generation)
        .sort((a, b) => a.created - b.created || a.id.localeCompare(b.id)),
    };
  });
}
export async function saveNotes(
  owner: string,
  notes: Schema["NoteResponse"][],
  keepIds?: number[],
  revision?: number,
): Promise<void> {
  await transaction("readwrite", async (tx) => {
    const current = await account(tx);
    if (
      current?.generation !== owner ||
      (revision !== undefined && current.revision !== revision)
    )
      return;
    const store = tx.objectStore("notes");
    for (const note of notes) store.put({ owner, id: note.id, note });
    const rows: StoredNote[] = await result(store.getAll());
    const retained = rows
      .filter(
        (row) => row.owner === owner && (!keepIds || keepIds.includes(row.id)),
      )
      .sort(
        (a, b) =>
          b.note.created_at.localeCompare(a.note.created_at) || b.id - a.id,
      )
      .slice(0, 50);
    const ids = new Set(retained.map((row) => row.id));
    for (const row of rows)
      if (row.owner !== owner || !ids.has(row.id))
        store.delete([row.owner, row.id]);
  });
  changed();
}
export async function enqueue(operation: Operation): Promise<void> {
  await transaction("readwrite", async (tx) => {
    if ((await account(tx))?.generation !== operation.owner)
      throw new Error("账号已切换，请重新打开笔记");
    const current = (await account(tx))!;
    tx.objectStore("meta").put(
      { ...current, revision: current.revision + 1 },
      "account",
    );
    const operations = tx.objectStore("operations");
    const existing: Operation | undefined = await result(
      operations.get(operation.id),
    );
    const queued: Operation[] = await result(operations.getAll());
    // Preserve insertion order even when two actions share a millisecond timestamp.
    const created =
      existing?.created ??
      Math.max(operation.created, ...queued.map((item) => item.created + 1));
    operations.put({ ...operation, created });
  });
  changed();
}
export async function completeOperation(operation: Operation): Promise<void> {
  await transaction("readwrite", async (tx) => {
    if ((await account(tx))?.generation !== operation.owner) return;
    const current = (await account(tx))!;
    tx.objectStore("meta").put(
      { ...current, revision: current.revision + 1 },
      "account",
    );
    tx.objectStore("operations").delete(operation.id);
    const noteId = Number(operation.path.match(/^\/notes\/(\d+)$/)?.[1]);
    const store = tx.objectStore("notes");
    if (noteId && operation.method === "DELETE")
      store.delete([operation.owner, noteId]);
    if (noteId && operation.method === "PATCH") {
      const row: StoredNote | undefined = await result(
        store.get([operation.owner, noteId]),
      );
      if (row) {
        row.note.is_favorite = JSON.parse(operation.body!).is_favorite;
        store.put(row);
      }
    }
  });
  changed();
}
export function applyOperations(
  notes: Schema["NoteResponse"][],
  operations: Operation[],
): Schema["NoteResponse"][] {
  let result = notes.map((note) => ({ ...note }));
  for (const operation of operations) {
    const id = Number(operation.path.match(/^\/notes\/(\d+)$/)?.[1]);
    if (operation.method === "DELETE")
      result = result.filter((note) => note.id !== id);
    if (operation.method === "PATCH")
      result = result.map((note) =>
        note.id === id
          ? { ...note, is_favorite: JSON.parse(operation.body!).is_favorite }
          : note,
      );
  }
  return result;
}

export async function discardOperation(operation: Operation): Promise<void> {
  await transaction("readwrite", async (tx) => {
    const current = await account(tx);
    if (current?.generation !== operation.owner) return;
    tx.objectStore("operations").delete(operation.id);
    tx.objectStore("meta").put(
      { ...current, revision: current.revision + 1 },
      "account",
    );
  });
  changed();
  if (typeof window !== "undefined")
    window.dispatchEvent(new Event("clipo:synced"));
}
