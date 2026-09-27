// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useRef, useState } from "react";
import { refreshApplication, watchServiceWorkerUpdates } from "@/lib/pwa";
import packageInfo from "@/package.json";

export function Pwa() {
  const registration = useRef<ServiceWorkerRegistration>();
  const refreshCleanup = useRef<() => void>();
  const [workerUpdate, setWorkerUpdate] = useState(false);
  const [newVersion, setNewVersion] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  useEffect(() => {
    if (
      process.env.NODE_ENV !== "production" ||
      !("serviceWorker" in navigator)
    )
      return;
    let active = true;
    let stopWatching: (() => void) | undefined;
    void navigator.serviceWorker
      .register("/sw.js", { scope: "/", updateViaCache: "none" })
      .then((value) => {
        if (!active) return;
        registration.current = value;
        stopWatching = watchServiceWorkerUpdates(
          value,
          navigator.serviceWorker,
          setWorkerUpdate,
        );
      })
      .catch(() => undefined);
    const check = () => {
      void registration.current?.update().catch(() => undefined);
      void fetch("/api/v1/meta/version", { cache: "no-store" })
        .then((response) => (response.ok ? response.json() : null))
        .then((meta) => {
          if (active && meta?.version)
            setNewVersion(meta.version !== packageInfo.version);
        })
        .catch(() => undefined);
    };
    check();
    const interval = setInterval(check, 60000);
    return () => {
      active = false;
      clearInterval(interval);
      stopWatching?.();
      refreshCleanup.current?.();
      registration.current = undefined;
    };
  }, []);
  if (!workerUpdate && !newVersion && !refreshing) return null;
  function refresh() {
    if (refreshCleanup.current) return;
    setRefreshing(true);
    refreshCleanup.current = refreshApplication(
      registration.current,
      navigator.serviceWorker,
      () => location.reload(),
    );
  }
  return (
    <div className="update-notice" role="status">
      有新版本，刷新后使用。{" "}
      <button className="inline-button" onClick={refresh} disabled={refreshing}>
        {refreshing ? "正在刷新…" : "刷新应用"}
      </button>
    </div>
  );
}
