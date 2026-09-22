// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
const result = document.querySelector("#result");
const capture = document.querySelector("#capture");
const note = document.querySelector("#note");
let tab;
let submitting = false;
let checking = false;
async function refresh() {
  if (checking) return;
  checking = true;
  try {
    const state = await chrome.runtime.sendMessage({ type: "state" });
    if (!state?.ok) return;
    if (state.status) {
      result.textContent = state.status.message;
      result.classList.toggle("error", state.status.phase === "error");
    }
    document.querySelector("#pending").hidden = !state.pending;
    document.querySelector("#pending-count").textContent =
      `${state.pending} 项内容已暂存，网络恢复后点击重试。`;
    const jobs = document.querySelector("#jobs");
    jobs.hidden = !state.server;
    if (state.server) jobs.href = state.server + "/jobs/";
    capture.disabled = submitting || state.working || !tab?.id;
    document.querySelector("#resume").disabled = state.working;
    document.querySelector("#clear").disabled = state.working;
    if (state.status?.phase === "accepted") {
      const answer = await chrome.runtime.sendMessage({ type: "job" });
      if (answer?.job) {
        const job = answer.job;
        if (job.status === "success") {
          result.textContent = "笔记已保存。";
          note.hidden = !job.note_id;
          note.href = answer.server + "/notes/?id=" + job.note_id;
        } else if (job.status === "failed") {
          result.textContent = "后台整理失败，请打开保存队列查看原因并重试。";
          result.classList.add("error");
        }
      }
    } else note.hidden = true;
  } finally {
    checking = false;
  }
}
async function send(message) {
  submitting = true;
  capture.disabled = true;
  try {
    const answer = await chrome.runtime.sendMessage(message);
    if (!answer?.ok) {
      result.textContent = answer?.message || "操作中断，请重试";
      result.classList.add("error");
    }
  } catch {
    result.textContent = "操作中断，重新打开窗口后可重试已暂存内容。";
  } finally {
    submitting = false;
    capture.disabled = false;
    await refresh();
  }
}
[tab] = await chrome.tabs.query({ active: true, currentWindow: true });
document.querySelector("#page-title").textContent = tab?.title || "当前页面";
capture.addEventListener("click", () => {
  const tags = document
    .querySelector("#tags")
    .value.split(/[,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
  void send({ type: "capture", tabId: tab?.id, tags });
});
document
  .querySelector("#resume")
  .addEventListener("click", () => void send({ type: "resume" }));
document
  .querySelector("#clear")
  .addEventListener("click", () => void send({ type: "clear" }));
document
  .querySelector("#options")
  .addEventListener("click", () => chrome.runtime.openOptionsPage());
await refresh();
setInterval(() => {
  void refresh().catch(() => {});
}, 1800);
