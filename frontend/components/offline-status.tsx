"use client";
import { useEffect, useState } from "react";
import { prefetchNotes, syncOffline } from "@/lib/offline-sync";
import { connectionAvailable } from "@/lib/notes";
import {
  readOffline,
  discardOperation,
  type Operation,
} from "@/lib/offline-store";

export function OfflineStatus() {
  const [online, setOnline] = useState(true);
  const [count, setCount] = useState(0);
  const [cached, setCached] = useState(0);
  const [error, setError] = useState("");
  const [failed, setFailed] = useState<Operation | undefined>();
  useEffect(() => {
    let active = true;
    const update = () => {
      setOnline(connectionAvailable());
      void readOffline()
        .then((local) => {
          if (!active) return;
          setFailed(local.operations.find((operation) => operation.error));
          setCount(local.operations.length);
          setCached(local.notes.length);
          setError(
            local.operations.find((operation) => operation.error)?.error ?? "",
          );
        })
        .catch(() => {
          if (active) setError("浏览器未允许离线存储，联网阅读仍可使用。");
        });
    };
    const connect = () => {
      update();
      void syncOffline().then(prefetchNotes);
    };
    update();
    connect();
    window.addEventListener("online", connect);
    window.addEventListener("offline", update);
    window.addEventListener("clipo:connection", update);
    window.addEventListener("clipo:offline-changed", update);
    const interval = setInterval(connect, 60000);
    // Some devices restore connectivity without an online event (e.g. a waking PWA).
    const retry = setInterval(() => {
      if (!document.hidden && navigator.onLine) void syncOffline();
    }, 5000);
    return () => {
      active = false;
      clearInterval(interval);
      clearInterval(retry);
      window.removeEventListener("online", connect);
      window.removeEventListener("offline", update);
      window.removeEventListener("clipo:connection", update);
      window.removeEventListener("clipo:offline-changed", update);
    };
  }, []);
  return (
    <div className="offline-status" role="status">
      {!online
        ? `离线阅读 · 已缓存 ${cached} / 50 篇`
        : `离线可读 ${cached} / 50 篇`}
      {count > 0 && (
        <span>
          {" "}
          · {count} 项操作待同步{error ? `：${error}` : ""}{" "}
          <button
            className="inline-button"
            onClick={() => void syncOffline().then(prefetchNotes)}
          >
            重试同步
          </button>
        </span>
      )}
      {failed && (
        <button
          className="inline-button"
          onClick={async () => {
            if (
              window.confirm("取消这项失败操作？其他待同步操作会继续执行。")
            ) {
              await discardOperation(failed);
              await syncOffline();
            }
          }}
        >
          取消失败操作
        </button>
      )}
      {!count && error && <span> · {error}</span>}
      {!online && (
        <span> · 收藏和删除将在联网后同步；标签与设置需联网修改。</span>
      )}
    </div>
  );
}
