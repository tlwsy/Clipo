// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const session = {
  access_token: "fresh-access",
  refresh_token: "not-stored-in-javascript",
  expires_in: 900,
  user: {
    id: 1,
    username: "admin",
    email: "admin@example.com",
    is_admin: true,
  },
};

function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("authenticated API client", () => {
  it("renews authentication for binary downloads and preserves JSON errors", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({}, 401))
      .mockResolvedValueOnce(response(session))
      .mockResolvedValueOnce(new Response("ZIP bytes"))
      .mockResolvedValueOnce(
        response(
          { error: { code: "backup_expired", message: "请重新导出" } },
          410,
        ),
      );
    vi.stubGlobal("fetch", fetch);
    const { api, acceptSession } = await import("./api");
    acceptSession({ ...session, access_token: "expired" });
    const blob = await api<Blob>("/backups/test/download", {
      responseType: "blob",
    });
    expect(await blob.text()).toBe("ZIP bytes");
    expect(fetch.mock.calls[2][1].headers.get("Authorization")).toBe(
      "Bearer fresh-access",
    );
    await expect(
      api("/backups/test/download", { responseType: "blob" }),
    ).rejects.toMatchObject({ code: "backup_expired" });
  });
  beforeEach(() => {
    vi.resetModules();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("preserves field validation details so the setup wizard can identify the account error", async () => {
    const detail = {
      fields: [
        {
          field: "body.email",
          type: "value_error",
          message: "请输入有效的邮箱地址",
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            error: {
              code: "validation_error",
              message: "请输入有效的邮箱地址",
              detail,
            },
          },
          422,
        ),
      ),
    );
    const { api } = await import("./api");
    await expect(
      api("/setup/validate", {
        authenticated: false,
        method: "POST",
        body: "{}",
      }),
    ).rejects.toMatchObject({
      status: 422,
      message: "请输入有效的邮箱地址",
      detail,
    });
  });

  it("retries an expired access token after silently rotating the cookie session", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({}, 401))
      .mockResolvedValueOnce(response(session))
      .mockResolvedValueOnce(response(session.user));
    vi.stubGlobal("fetch", fetch);
    const { api, acceptSession } = await import("./api");
    acceptSession({ ...session, access_token: "expired-access" });
    expect(await api("/auth/me")).toEqual(session.user);
    expect(fetch.mock.calls.map((call) => call[0])).toEqual([
      "/api/v1/auth/me",
      "/api/v1/auth/refresh",
      "/api/v1/auth/me",
    ]);
    expect(fetch.mock.calls[1][1].body).toBe("{}");
    expect(fetch.mock.calls[2][1].headers.get("Authorization")).toBe(
      "Bearer fresh-access",
    );
  });

  it("shares a single refresh when authenticated requests arrive together", async () => {
    let finishRefresh!: (value: Response) => void;
    const fetch = vi.fn().mockImplementation((url: string) =>
      url.endsWith("/refresh")
        ? new Promise<Response>((resolve) => {
            finishRefresh = resolve;
          })
        : Promise.resolve(response({ ok: true })),
    );
    vi.stubGlobal("fetch", fetch);
    const { api } = await import("./api");
    const pending = Promise.all([api("/settings"), api("/tokens")]);
    expect(fetch).toHaveBeenCalledTimes(1);
    finishRefresh(response(session));
    await pending;
    expect(
      fetch.mock.calls.filter((call) => call[0].endsWith("/refresh")),
    ).toHaveLength(1);
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("does not loop or retry protected requests after refresh is rejected", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        response(
          { error: { code: "invalid_refresh_token", message: "请重新登录" } },
          401,
        ),
      );
    vi.stubGlobal("fetch", fetch);
    const { api, ApiError } = await import("./api");
    await expect(api("/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps public login errors separate from session renewal", async () => {
    const fetch = vi.fn().mockResolvedValue(
      response(
        {
          error: { code: "invalid_credentials", message: "用户名或密码错误" },
        },
        401,
      ),
    );
    vi.stubGlobal("fetch", fetch);
    const { api } = await import("./api");
    await expect(
      api("/auth/login", { authenticated: false, method: "POST", body: "{}" }),
    ).rejects.toMatchObject({ code: "invalid_credentials" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("handles successful empty responses when revoking a token", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    const { api, acceptSession } = await import("./api");
    acceptSession(session);
    expect(await api("/tokens/1", { method: "DELETE" })).toBeUndefined();
  });

  it("waits for refresh to finish before clearing the server session on logout", async () => {
    let finishRefresh!: (value: Response) => void;
    const fetch = vi.fn().mockImplementation((url: string) =>
      url.endsWith("/refresh")
        ? new Promise<Response>((resolve) => {
            finishRefresh = resolve;
          })
        : Promise.resolve(new Response(null, { status: 204 })),
    );
    vi.stubGlobal("fetch", fetch);
    const { refreshSession, logout } = await import("./api");
    const refreshing = refreshSession();
    const loggingOut = logout();
    expect(fetch).toHaveBeenCalledTimes(1);
    finishRefresh(response(session));
    await Promise.all([refreshing, loggingOut]);
    expect(fetch.mock.calls[1][0]).toBe("/api/v1/auth/logout");
  });
});
