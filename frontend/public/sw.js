// Phase 2 enables installation and share targets. Offline data storage is Phase 4.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => new Response(
      '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Clipo · 无法连接</title><body style="font:16px system-ui;padding:32px;color:#24372f"><h1>暂时无法连接 Clipo</h1><p>请连接网络后重试，已有笔记仍保存在服务器上。</p><button onclick="location.reload()">重新连接</button></body></html>',
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } },
    )));
  }
});
