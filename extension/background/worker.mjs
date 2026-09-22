// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { collectPage } from "../content/extract.mjs";
import {
  ApiError,
  MAX_BYTES,
  originPermission,
  request,
  serverAddress,
  submit,
} from "../lib/api.mjs";
import * as queue from "../lib/store.mjs";

const ready = chrome.storage.local.setAccessLevel({
  accessLevel: "TRUSTED_CONTEXTS",
});
let active = Promise.resolve();
let working = 0;
function serialized(task) {
  working += 1;
  const next = active
    .then(() => ready)
    .then(task)
    .finally(() => {
      working -= 1;
    });
  active = next.catch(() => {});
  return next;
}
const status = (value) =>
  chrome.storage.local.set({ status: { ...value, time: Date.now() } });
async function badge(text, color = "#237466") {
  await chrome.action.setBadgeBackgroundColor({ color });
  await chrome.action.setBadgeText({ text });
}
async function config() {
  const value = (await chrome.storage.local.get("config")).config;
  if (!value)
    throw new ApiError("请先打开扩展设置，填写服务器地址与 API Token");
  if (
    !(await chrome.permissions.contains({
      origins: [originPermission(value.server)],
    }))
  ) {
    throw new ApiError("服务器访问权限已移除，请打开设置重新授权");
  }
  return value;
}
async function report(error) {
  const message =
    error instanceof ApiError
      ? error.message
      : "保存未完成，请重试；若页面已切换，请重新打开目标页面";
  await status({ phase: "error", message });
  await badge("!", "#b34036");
  return { ok: false, message };
}
async function flush(current) {
  for (const item of await queue.pending()) {
    if (item.configId !== current.id) {
      await queue.remove(item.id);
      continue;
    }
    await status({ phase: "uploading", message: "正在提交页面内容…" });
    const job = await submit(current, item, queue.save);
    await queue.remove(item.id);
    await status({
      phase: "accepted",
      message: "已提交，Clipo 正在后台整理。",
      jobId: job.job_id,
    });
    await badge("✓");
  }
}
async function capture(tabId, tags = [], selection = "") {
  const current = await config();
  if ((await queue.pending()).length >= 3)
    throw new ApiError("本机还有待提交内容，请先重试或清除队列");
  if (
    !Array.isArray(tags) ||
    tags.length > 20 ||
    tags.some(
      (tag) => typeof tag !== "string" || !tag.trim() || tag.length > 50,
    )
  ) {
    throw new ApiError("最多填写 20 个标签，每个不超过 50 字");
  }
  await status({
    phase: "reading",
    message: "正在读取当前页面，平台评论加载可能需要十几秒…",
  });
  await badge("…");
  const settings = await request(current, "/settings");
  let result;
  try {
    [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: collectPage,
      args: [settings.capture.max_comments, selection],
    });
  } catch {
    throw new ApiError(
      "无法读取此页面；请打开普通 HTTP(S) 网页或帖子详情，再点击扩展保存",
    );
  }
  if (result?.result?.error) throw new ApiError(result.result.error);
  const captured = result?.result;
  if (!captured?.payload)
    throw new ApiError("页面读取中断，请保持目标页面打开并重试");
  captured.payload.tags = [...new Set(tags.map((tag) => tag.trim()))];
  const bytes = new TextEncoder().encode(JSON.stringify(captured.payload));
  if (bytes.length > MAX_BYTES)
    throw new ApiError("页面超过 20 MiB，请缩小内容后保存");
  await queue.save({
    id: crypto.randomUUID(),
    configId: current.id,
    url: captured.url,
    bytes,
  });
  await flush(current);
  return { ok: true };
}
async function configure(message) {
  let server;
  try {
    server = serverAddress(message.server);
  } catch (error) {
    throw new ApiError(error.message);
  }
  const token = message.token?.trim();
  if (!token?.startsWith("ct_") || token.length > 256)
    throw new ApiError("请填写 Clipo 设置页生成的完整 API Token");
  if (
    !(await chrome.permissions.contains({
      origins: [originPermission(server)],
    }))
  )
    throw new ApiError("请允许扩展访问所填服务器");
  const user = await request({ server, token }, "/auth/me");
  await request({ server, token }, "/settings");
  const old = (await chrome.storage.local.get("config")).config;
  const changed = old?.server !== server || old?.token !== token;
  if (message.type === "test")
    return { ok: true, message: `连接成功：${user.username}` };
  if (changed) await queue.clear();
  await chrome.storage.local.set({
    config: { server, token, id: changed ? crypto.randomUUID() : old.id },
  });
  if (changed) {
    await status({ phase: "idle", message: "配置已保存，可以开始收藏网页。" });
    await badge("");
  }
  return { ok: true, message: "配置已保存，连接正常。" };
}
async function handle(message) {
  if (["configure", "test"].includes(message.type)) return configure(message);
  if (message.type === "state") {
    const { status: last, config: current } = await chrome.storage.local.get([
      "status",
      "config",
    ]);
    return {
      ok: true,
      status: last,
      server: current?.server,
      pending: (await queue.pending()).length,
      working: working > 0,
    };
  }
  if (message.type === "capture") return capture(message.tabId, message.tags);
  if (message.type === "resume") {
    await flush(await config());
    return { ok: true };
  }
  if (message.type === "clear") {
    await queue.clear();
    await status({
      phase: "idle",
      message: "本机待提交内容已清除；已被服务器接收的任务仍可在保存队列查看。",
    });
    await badge("");
    return { ok: true };
  }
  if (message.type === "job") {
    const current = await config();
    const { status: last } = await chrome.storage.local.get("status");
    if (!last?.jobId) return { ok: true };
    const job = await request(
      current,
      `/jobs/${encodeURIComponent(last.jobId)}`,
    );
    return { ok: true, job, server: current.server };
  }
  throw new ApiError("扩展请求无效，请重新打开窗口");
}
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  const allowed = [
    chrome.runtime.getURL("popup/index.html"),
    chrome.runtime.getURL("options/index.html"),
  ];
  if (sender.id !== chrome.runtime.id || !allowed.includes(sender.url))
    return false;
  if (
    ["configure", "test"].includes(message?.type) &&
    sender.url !== allowed[1]
  )
    return false;
  // Status reads do not wait behind slow uploads; popup can be closed and reopened.
  const task =
    message?.type === "state"
      ? ready.then(() => handle(message))
      : serialized(() => handle(message));
  task.catch(report).then(respond);
  return true;
});
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll().then(() =>
    chrome.contextMenus.create({
      id: "save",
      title: "保存到 Clipo",
      contexts: ["page", "selection"],
      documentUrlPatterns: ["http://*/*", "https://*/*"],
    }),
  );
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "save" && tab?.id)
    serialized(() => capture(tab.id, [], info.selectionText || "")).catch(
      report,
    );
});
chrome.runtime.onStartup.addListener(() => {
  serialized(async () => {
    if ((await queue.pending()).length) await flush(await config());
  }).catch(report);
});
