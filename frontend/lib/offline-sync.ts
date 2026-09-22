// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { ApiError, errorMessage, type Schema } from "./api";
import { timedApi } from "./notes";
import {
  completeOperation,
  enqueue,
  readAccount,
  readOffline,
  saveNotes,
} from "./offline-store";

let running: Promise<void> | null = null;
let rerun = false;
let precaching: Promise<void> | null = null;

async function replay(): Promise<void> {
  if (!navigator.onLine) return;
  const local = await readOffline();
  if (!local.account || !local.operations.length) return;
  const user = await timedApi<Schema["UserResponse"]>("/auth/me");
  if (
    user.id !== local.account.user.id ||
    user.username !== local.account.user.username
  )
    return;
  for (const operation of local.operations) {
    if ((await readAccount())?.generation !== operation.owner) return;
    try {
      await timedApi(operation.path, {
        method: operation.method,
        body: operation.body,
        headers: { "Idempotency-Key": operation.id },
        expectedUserId: local.account.user.id,
      });
      await completeOperation(operation);
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.status === 404 &&
        operation.method === "DELETE"
      ) {
        await completeOperation(operation);
        continue;
      }
      if (error instanceof ApiError && error.status === 401) return;
      await enqueue({ ...operation, error: errorMessage(error) });
      return;
    }
  }
  window.dispatchEvent(new Event("clipo:synced"));
}
export async function syncOffline(): Promise<void> {
  if (running) {
    rerun = true;
    return running;
  }
  running = (async () => {
    do {
      rerun = false;
      try {
        if (navigator.locks)
          await navigator.locks.request("clipo-offline-sync", replay);
        else await replay();
      } catch {
        /* A later connection event or manual retry will resume the durable queue. */
      }
    } while (rerun);
  })().finally(() => {
    running = null;
  });
  return running;
}
export async function prefetchNotes(): Promise<void> {
  if (precaching) return precaching;
  precaching = (async () => {
    const owner = await readAccount();
    if (!owner || !navigator.onLine) return;
    const page = await timedApi<Schema["NotePage"]>("/notes?limit=50", {
      expectedUserId: owner.user.id,
    });
    const notes: Schema["NoteResponse"][] = [];
    const pending = [...page.items];
    await Promise.all(
      Array.from({ length: 4 }, async () => {
        while (pending.length) {
          const item = pending.shift()!;
          if ((await readAccount())?.generation !== owner.generation) return;
          try {
            notes.push(
              await timedApi<Schema["NoteResponse"]>(`/notes/${item.id}`, {
                expectedUserId: owner.user.id,
              }),
            );
          } catch (error) {
            if (!(error instanceof ApiError && error.status === 404))
              throw error;
          }
        }
      }),
    );
    await saveNotes(
      owner.generation,
      notes,
      page.items.map((item) => item.id),
      owner.revision,
    );
  })()
    .catch(() => undefined)
    .finally(() => {
      precaching = null;
    });
  return precaching;
}
