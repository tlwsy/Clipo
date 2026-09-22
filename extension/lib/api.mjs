// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
export const DIRECT_BYTES = 5 * 1024 * 1024;
export const MAX_BYTES = 20 * 1024 * 1024;
export const CHUNK_BYTES = 256 * 1024;

export function serverAddress(value) {
  let url;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error("请输入完整的服务器地址，例如 https://clipo.example.com");
  }
  if (
    !["https:", "http:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  ) {
    throw new Error(
      "服务器地址仅填写 HTTP(S) 协议、主机与端口，不要附带路径或凭据",
    );
  }
  if (
    url.protocol === "http:" &&
    !/^(localhost|127\.0\.0\.1|\[::1\]|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(
      url.hostname,
    )
  ) {
    throw new Error("公网服务器请使用 HTTPS；HTTP 仅用于本机或内网测试");
  }
  return url.origin;
}

export function originPermission(server) {
  const url = new URL(server);
  return url.protocol + "//" + url.hostname + "/*";
}

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.status = status;
  }
}

export async function request(
  config,
  path,
  { method = "GET", json, bytes, key } = {},
) {
  const headers = { "X-Clipo-Token": config.token };
  if (key) headers["Idempotency-Key"] = key;
  if (json !== undefined) headers["Content-Type"] = "application/json";
  if (bytes) headers["Content-Type"] = "application/octet-stream";
  let response;
  try {
    response = await fetch(config.server + "/api/v1" + path, {
      method,
      headers,
      body: json !== undefined ? JSON.stringify(json) : bytes,
      credentials: "omit",
      redirect: "error",
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
  } catch {
    throw new ApiError("连接失败，请检查服务器、证书与网络后重试");
  }
  if (!response.ok) {
    // Never surface raw upstream bodies, URLs or credentials in extension UI/logs.
    const messages = {
      401: "API Token 已失效，请在设置中重新配置",
      403: "服务器拒绝访问，请检查权限",
      404: "接口或任务不存在，请更新 Clipo 服务端",
      409: "提交状态冲突，请重试或重新保存页面",
      410: "上传已过期，请重新保存页面",
      413: "服务器拒绝较大内容，请检查代理请求体限制",
      422: "页面内容格式不符合要求，请检查页面或更新扩展",
      429: "请求过于频繁，请稍后重试",
    };
    throw new ApiError(
      messages[response.status] || "服务器暂不可用，请稍后重试",
      response.status,
    );
  }
  return response.status === 204 ? null : response.json();
}

export async function digest(bytes) {
  return Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (n) => n.toString(16).padStart(2, "0"),
  ).join("");
}

export async function submit(config, item, checkpoint, call = request) {
  const payload = JSON.parse(new TextDecoder().decode(item.bytes));
  const body = { url: item.url, payload };
  if (new TextEncoder().encode(JSON.stringify(body)).length <= DIRECT_BYTES) {
    return call(config, "/captures", {
      method: "POST",
      json: body,
      key: item.id,
    });
  }
  if (item.bytes.length > MAX_BYTES)
    throw new ApiError("页面超过 20 MiB，请缩小内容后重新保存", 413);
  if (!item.jobId) {
    const job = await call(config, "/captures/uploads", {
      method: "POST",
      key: item.id,
      json: {
        url: item.url,
        total_bytes: item.bytes.length,
        sha256: await digest(item.bytes),
      },
    });
    if (job.status !== "uploading") return job;
    item.jobId = job.job_id;
    await checkpoint(item);
  }
  for (
    let index = item.nextChunk || 0;
    index * CHUNK_BYTES < item.bytes.length;
    index++
  ) {
    await call(config, `/captures/${item.jobId}/chunks/${index}`, {
      method: "PUT",
      bytes: item.bytes.slice(index * CHUNK_BYTES, (index + 1) * CHUNK_BYTES),
    });
    item.nextChunk = index + 1;
    await checkpoint(item);
  }
  return call(config, `/captures/${item.jobId}/complete`, { method: "POST" });
}
