// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The static export script replaces these values with this build's manifest. */
const VERSION = "__CLIPO_BUILD__";
const PRECACHE = /* __CLIPO_PRECACHE__ */ [];
const CACHE = `clipo-shell-${VERSION}`;
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)));
});
self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") event.waitUntil(self.skipWaiting());
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) {
        if (name.startsWith("clipo-shell-") && name !== CACHE)
          await caches.delete(name);
      }
      await self.clients.claim();
    })(),
  );
});
async function networkFirst(request, key) {
  const cache = await caches.open(CACHE);
  let timer;
  const network = fetch(request);
  try {
    return await Promise.race([
      network,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("timeout")), 2000);
      }),
    ]);
  } catch {
    const cached = await cache.match(key);
    if (cached) return cached;
    return new Response("离线页面尚未准备好，请联网后重试。", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  } finally {
    clearTimeout(timer);
  }
}
async function shell(request, key) {
  // HTML and RSC belong to the same installed build. Serving the cached shell
  // avoids a network round trip; the update prompt activates the next build.
  const cached = await (await caches.open(CACHE)).match(key);
  return cached ?? networkFirst(request, key);
}
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Private API data is managed by the account-scoped IndexedDB store, never Cache Storage.
  if (
    url.origin !== self.location.origin ||
    event.request.method !== "GET" ||
    url.pathname.startsWith("/api/")
  )
    return;
  if (event.request.mode === "navigate") {
    const path = url.pathname.endsWith("/") ? url.pathname : `${url.pathname}/`;
    event.respondWith(shell(event.request, path));
  } else if (event.request.headers.get("RSC") === "1") {
    const path = url.pathname.replace(/\/$/, "");
    event.respondWith(shell(event.request, `${path}/index.txt`));
  } else if (
    url.pathname.startsWith("/_next/static/") ||
    PRECACHE.includes(url.pathname)
  ) {
    event.respondWith(
      caches
        .open(CACHE)
        .then(
          async (cache) =>
            (await cache.match(url.pathname)) ?? fetch(event.request),
        ),
    );
  }
});
