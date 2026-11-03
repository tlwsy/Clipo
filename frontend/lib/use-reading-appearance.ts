// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useState, useSyncExternalStore } from "react";
import { loadOnlineFont } from "./reading-fonts";
import { readingVariables, type ReadingStyle } from "./reading";
const query = "(prefers-color-scheme: dark)";
function subscribe(callback: () => void) {
  const media = window.matchMedia(query);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}
export function useReadingAppearance(style: ReadingStyle, sample = "阅读时光") {
  const dark = useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  );
  const [attempt, setAttempt] = useState(0);
  const [font, setFont] = useState({ key: "", status: "idle", message: "" });
  const online = style.font_family === "online" ? style.online_font : null;
  const key = JSON.stringify([online, style.font_weight, sample.slice(0, 80)]);
  useEffect(() => {
    if (!online) return;
    let active = true;
    setFont({ key, status: "loading", message: "正在下载字体…" });
    void loadOnlineFont(online, style.font_weight, sample)
      .then(() => {
        if (active) setFont({ key, status: "ready", message: "字体已就绪" });
      })
      .catch(() => {
        if (active)
          setFont({
            key,
            status: "error",
            message: "在线字体未能加载，暂用本机字体。",
          });
      });
    return () => {
      active = false;
    };
    // The serialized key includes all font metadata, weight and preview sample.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);
  return {
    variables: readingVariables(style, dark),
    dark,
    fontStatus: online ? (font.key === key ? font.status : "loading") : "idle",
    fontMessage: online ? font.message : "",
    retryFont: () => setAttempt((value) => value + 1),
  };
}
