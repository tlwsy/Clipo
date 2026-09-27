// SPDX-License-Identifier: AGPL-3.0-or-later

export function watchServiceWorkerUpdates(
  registration: ServiceWorkerRegistration,
  workers: ServiceWorkerContainer,
  onUpdate: (available: boolean) => void,
): () => void {
  let controller = workers.controller;
  const observed = new Set<ServiceWorker>();
  const inspect = () => {
    for (const worker of [registration.installing, registration.waiting]) {
      if (worker && !observed.has(worker)) {
        observed.add(worker);
        worker.addEventListener("statechange", inspect);
      }
    }
    // 首次安装与首次接管页面不属于升级。
    controller ??= workers.controller;
    onUpdate(
      controller !== null &&
        (registration.waiting?.state === "installed" ||
          (workers.controller !== null && workers.controller !== controller)),
    );
  };
  registration.addEventListener("updatefound", inspect);
  workers.addEventListener("controllerchange", inspect);
  inspect();
  return () => {
    registration.removeEventListener("updatefound", inspect);
    workers.removeEventListener("controllerchange", inspect);
    for (const worker of observed)
      worker.removeEventListener("statechange", inspect);
  };
}

export function refreshApplication(
  registration: ServiceWorkerRegistration | undefined,
  workers: ServiceWorkerContainer,
  reload: () => void,
): () => void {
  // 点击时读取实时状态；其他窗口可能已激活更新。
  const waiting = registration?.waiting;
  if (!waiting || waiting.state !== "installed") {
    reload();
    return () => undefined;
  }
  let finished = false;
  const cleanup = () => {
    clearTimeout(timer);
    workers.removeEventListener("controllerchange", finish);
    waiting.removeEventListener("statechange", inspect);
  };
  const finish = () => {
    if (finished) return;
    finished = true;
    cleanup();
    reload();
  };
  const inspect = () => {
    if (waiting.state === "activated" || waiting.state === "redundant")
      finish();
  };
  // PWA 没有浏览器刷新栏；事件丢失时也要结束等待并重新加载。
  const timer = setTimeout(finish, 5000);
  workers.addEventListener("controllerchange", finish);
  waiting.addEventListener("statechange", inspect);
  try {
    waiting.postMessage({ type: "SKIP_WAITING" });
  } catch {
    finish();
  }
  return cleanup;
}
