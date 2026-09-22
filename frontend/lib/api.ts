// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { captureKey } from "./share";
import type { components } from "./api-types";

export type Schema = components["schemas"];

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail: Schema["ErrorDetail"] = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let accessToken: string | null = null;
let sessionUserId: number | null = null;
let pendingRefresh: Promise<Schema["SessionResponse"]> | null = null;

export function acceptSession(session: Schema["SessionResponse"]): void {
  // Access tokens live in memory. The server keeps refresh tokens in an HttpOnly cookie.
  accessToken = session.access_token;
  sessionUserId = session.user.id;
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "request_failed",
      payload?.error?.message ?? "请求未成功，请稍后重试",
      payload?.error?.detail ?? {},
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function refreshSession(): Promise<Schema["SessionResponse"]> {
  if (!pendingRefresh) {
    const refresh = async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      try {
        const response = await fetch("/api/v1/auth/refresh", {
          signal: controller.signal,
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        const session = await parse<Schema["SessionResponse"]>(response);
        acceptSession(session);
        return session;
      } finally {
        clearTimeout(timeout);
      }
    };
    // Cookie rotation must also be serialized across browser tabs where supported.
    pendingRefresh = (async () => {
      if (typeof navigator !== "undefined" && navigator.locks) {
        return await navigator.locks.request("clipo-refresh", refresh);
      }
      return await refresh();
    })().finally(() => {
      pendingRefresh = null;
    });
  }
  return pendingRefresh;
}

export async function api<T>(
  path: string,
  options: RequestInit & {
    authenticated?: boolean;
    expectedUserId?: number;
    responseType?: "json" | "blob";
  } = {},
): Promise<T> {
  const {
    authenticated = true,
    expectedUserId,
    responseType = "json",
    ...init
  } = options;
  try {
    if (authenticated && !accessToken) await refreshSession();
    const request = () => {
      if (expectedUserId !== undefined && sessionUserId !== expectedUserId)
        throw new ApiError(
          409,
          "account_changed",
          "登录账号已改变，请刷新页面",
        );
      const headers = new Headers(init.headers);
      if (init.body && !headers.has("Content-Type"))
        headers.set("Content-Type", "application/json");
      if (authenticated && accessToken)
        headers.set("Authorization", `Bearer ${accessToken}`);
      return fetch(`/api/v1${path}`, {
        ...init,
        headers,
        credentials: "same-origin",
        cache: "no-store",
      });
    };
    const usedToken = accessToken;
    let response = await request();
    if (authenticated && response.status === 401) {
      // Another request may already have refreshed while this request was in flight.
      if (accessToken === usedToken) await refreshSession();
      response = await request();
    }
    if (response.ok && responseType === "blob")
      return (await response.blob()) as T;
    return await parse<T>(response);
  } catch (error) {
    if (authenticated && error instanceof ApiError && error.status === 401) {
      accessToken = null;
      sessionUserId = null;
      if (typeof window !== "undefined") {
        const { clearOffline } = await import("./offline-store");
        await clearOffline().catch(() => undefined);
        window.dispatchEvent(new Event("clipo:unauthorized"));
      }
    }
    throw error;
  }
}

export async function logout(): Promise<void> {
  // Finish any rotation first so it cannot overwrite the cookie after logout.
  if (pendingRefresh) await pendingRefresh.catch(() => undefined);
  await api<void>("/auth/logout", {
    method: "POST",
    body: "{}",
    authenticated: false,
  });
  accessToken = null;
  sessionUserId = null;
  if (typeof window !== "undefined") {
    const { clearOffline } = await import("./offline-store");
    await clearOffline().catch(() => undefined);
    localStorage.setItem("clipo:session", captureKey());
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "无法连接服务，请检查网络后重试";
}
