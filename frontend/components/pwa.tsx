"use client";
import { useEffect } from "react";

export function Pwa() {
  useEffect(() => {
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      void navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .catch(() => undefined);
    }
  }, []);
  return null;
}
