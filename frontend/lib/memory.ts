// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, type Schema } from "./api";

export type MemoryNote = Schema["MemoryNote"];

export async function loadMemories(
  userId: number,
  signal: AbortSignal,
): Promise<MemoryNote[]> {
  const result = await api<Schema["MemoryGallery"]>("/memory-gallery", {
    expectedUserId: userId,
    signal,
  });
  return result.notes;
}

export function dismissMemory(noteId: number, userId: number): Promise<void> {
  const body: Schema["MemoryDismiss"] = { note_id: noteId };
  return api("/memory-gallery/dismiss", {
    method: "POST",
    body: JSON.stringify(body),
    expectedUserId: userId,
  });
}

export function reportReading(
  noteId: number,
  userId: number,
  seconds: number,
): Promise<void> {
  const body: Schema["NoteView"] = { duration_seconds: seconds };
  return api(`/notes/${noteId}/view`, {
    method: "POST",
    body: JSON.stringify(body),
    expectedUserId: userId,
    keepalive: true,
  });
}

export function memorySwipe(
  dx: number,
  dy: number,
): "skip" | "favorite" | null {
  if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return null;
  return dx < 0 ? "skip" : "favorite";
}

// Only mounted note readers use this tracker. Fetching/caching a note does not.
export function trackReading(report: (seconds: number) => void): () => void {
  let last = performance.now();
  let milliseconds = 0;
  let pageActive = true;
  let opened = false;
  const canRead = () =>
    pageActive &&
    document.visibilityState === "visible" &&
    document.hasFocus() &&
    navigator.onLine;
  let active = canRead();

  const collect = () => {
    const now = performance.now();
    // A suspended device must not contribute hours when the timer resumes.
    if (active) milliseconds += Math.min(30000, Math.max(0, now - last));
    last = now;
  };
  const flush = () => {
    if (!navigator.onLine) {
      milliseconds = 0;
      return;
    }
    const seconds = Math.floor(milliseconds / 1000);
    if (seconds > 0 || (active && !opened)) {
      milliseconds -= seconds * 1000;
      opened = true;
      report(seconds);
    }
  };
  const refresh = () => {
    collect();
    active = canRead();
    flush();
  };
  const hide = () => {
    pageActive = false;
    refresh();
  };
  const show = () => {
    pageActive = true;
    refresh();
  };
  const events = ["focus", "blur", "online", "offline"] as const;
  for (const event of events) window.addEventListener(event, refresh);
  window.addEventListener("pagehide", hide);
  window.addEventListener("pageshow", show);
  document.addEventListener("visibilitychange", refresh);
  const timer = setInterval(refresh, 15000);
  flush();
  return () => {
    collect();
    active = false;
    flush();
    clearInterval(timer);
    for (const event of events) window.removeEventListener(event, refresh);
    window.removeEventListener("pagehide", hide);
    window.removeEventListener("pageshow", show);
    document.removeEventListener("visibilitychange", refresh);
  };
}
