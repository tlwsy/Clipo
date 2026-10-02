// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, ApiError, type Schema } from "./api";
import { loadNotes } from "./notes";
import { readAccount } from "./offline-store";

export type SearchFilters = {
  tag?: string;
  favorite?: boolean;
  cursor?: string;
};

export async function searchNotes(
  query: string,
  filters: SearchFilters,
  userId: number,
  signal: AbortSignal,
): Promise<Schema["SearchResponse"]> {
  const params = new URLSearchParams({ q: query, limit: "24" });
  if (filters.cursor) params.set("cursor", filters.cursor);
  if (filters.tag) params.set("tag_id", filters.tag);
  if (filters.favorite) params.set("favorite", "true");
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener("abort", abort, { once: true });
  if (signal.aborted) controller.abort();
  const timer = setTimeout(abort, 10000);
  try {
    if (typeof navigator !== "undefined" && !navigator.onLine)
      throw new TypeError("当前离线");
    return await api<Schema["SearchResponse"]>(`/notes/search?${params}`, {
      signal: controller.signal,
      expectedUserId: userId,
    });
  } catch (cause) {
    if (signal.aborted || (cause instanceof ApiError && cause.status < 500))
      throw cause;
    const owner = await readAccount().catch(() => undefined);
    if (owner && owner.user.id !== userId)
      throw new ApiError(409, "account_changed", "登录账号已改变，请刷新页面");
    const page = await loadNotes(`/notes?${params}`, userId);
    const after = await readAccount().catch(() => undefined);
    if (after && after.user.id !== userId)
      throw new ApiError(409, "account_changed", "登录账号已改变，请刷新页面");
    if (signal.aborted) throw new DOMException("搜索已取消", "AbortError");
    return {
      results: page.items.map((note) => ({
        ...note,
        match_type: "fulltext",
        score: 0,
      })),
      mode: "fulltext",
      semantic_status: "disabled",
      message:
        typeof navigator !== "undefined" && !navigator.onLine
          ? "当前离线，仅搜索此设备最近 50 篇缓存笔记，语义搜索需联网。"
          : "语义搜索暂不可用，已回退到关键词搜索；连接中断时仅查找本机缓存。",
    };
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", abort);
  }
}

export function waitForSearch(
  delay: number,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      reject(new DOMException("搜索已取消", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, delay);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
}
