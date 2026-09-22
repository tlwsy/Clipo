// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useState } from "react";
import packageInfo from "@/package.json";

export function Pwa() {
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null);
  const [newVersion, setNewVersion] = useState(false);
  useEffect(() => {
    if (
      process.env.NODE_ENV !== "production" ||
      !("serviceWorker" in navigator)
    )
      return;
    let active = true;
    let registration: ServiceWorkerRegistration | undefined;
    const inspect = () => {
      if (active && registration?.waiting) setWaiting(registration.waiting);
    };
    void navigator.serviceWorker
      .register("/sw.js", { scope: "/", updateViaCache: "none" })
      .then((value) => {
        registration = value;
        inspect();
        value.addEventListener("updatefound", () =>
          value.installing?.addEventListener("statechange", inspect),
        );
      })
      .catch(() => undefined);
    const check = () => {
      void registration?.update().catch(() => undefined);
      void fetch("/api/v1/meta/version", { cache: "no-store" })
        .then((response) => (response.ok ? response.json() : null))
        .then((meta) => {
          if (active && meta?.version && meta.version !== packageInfo.version)
            setNewVersion(true);
        })
        .catch(() => undefined);
    };
    check();
    const interval = setInterval(check, 60000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);
  if (!waiting && !newVersion) return null;
  function refresh() {
    if (waiting) {
      navigator.serviceWorker.addEventListener(
        "controllerchange",
        () => location.reload(),
        { once: true },
      );
      waiting.postMessage({ type: "SKIP_WAITING" });
    } else location.reload();
  }
  return (
    <div className="update-notice" role="status">
      有新版本，刷新后使用。{" "}
      <button className="inline-button" onClick={refresh}>
        刷新应用
      </button>
    </div>
  );
}
