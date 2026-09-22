// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { originPermission, serverAddress } from "../lib/api.mjs";
const form = document.querySelector("#settings");
const server = document.querySelector("#server");
const token = document.querySelector("#token");
const result = document.querySelector("#result");
const buttons = document.querySelectorAll("button");
const saved = (await chrome.storage.local.get("config")).config;
if (saved) {
  server.value = saved.server;
  token.value = saved.token;
}
async function send(type) {
  result.hidden = false;
  result.classList.remove("error");
  result.textContent = "正在连接…";
  buttons.forEach((button) => (button.disabled = true));
  try {
    const address = serverAddress(server.value);
    // Request only this host, inside the click gesture; no install-time site permission.
    if (
      !(await chrome.permissions.request({
        origins: [originPermission(address)],
      }))
    )
      throw new Error("未获得服务器访问权限，请点击按钮重新授权");
    const answer = await chrome.runtime.sendMessage({
      type,
      server: address,
      token: token.value,
    });
    if (!answer?.ok) throw new Error(answer?.message || "连接中断，请重试");
    result.textContent = answer.message;
    if (type === "configure") {
      const all = await chrome.permissions.getAll();
      const unused = (all.origins || []).filter(
        (origin) => origin !== originPermission(address),
      );
      if (unused.length) await chrome.permissions.remove({ origins: unused });
    }
  } catch (error) {
    result.classList.add("error");
    result.textContent = error.message || "连接中断，请重试";
  } finally {
    buttons.forEach((button) => (button.disabled = false));
  }
}
form.addEventListener("submit", (event) => {
  event.preventDefault();
  void send("configure");
});
document.querySelector("#test").addEventListener("click", () => {
  if (form.reportValidity()) void send("test");
});
