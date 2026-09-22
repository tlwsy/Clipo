// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { saveCapture } from "@/lib/notes";
import { errorMessage } from "@/lib/api";
import {
  clearShare,
  extractSharedUrl,
  pendingShare,
  rememberShare,
} from "@/lib/share";

function SaveShared({
  capture,
}: {
  capture: { url: string; key: string } | null;
}) {
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const router = useRouter();
  useEffect(() => {
    if (!capture) return;
    let active = true;
    setError("");
    saveCapture(capture.url, capture.key)
      .then(() => {
        if (active) {
          clearShare();
          router.replace("/jobs/");
        }
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      });
    return () => {
      active = false;
    };
  }, [capture, attempt, router]);
  return (
    <section className="empty-state">
      <h1>{capture ? "保存分享的网页" : "没有找到网页链接"}</h1>
      {capture ? (
        <>
          <p className="shared-url">{capture.url}</p>
          {error ? (
            <>
              <div className="notice error" role="alert">
                {error}
              </div>
              <button
                className="button"
                onClick={() => setAttempt((value) => value + 1)}
              >
                重新提交
              </button>
            </>
          ) : (
            <p role="status">正在加入保存队列…</p>
          )}
        </>
      ) : (
        <p>请从浏览器分享公开网页，或返回首页粘贴链接。</p>
      )}
      <Link href="/" className="text-link" onClick={clearShare}>
        返回笔记
      </Link>
    </section>
  );
}
export default function SharePage() {
  const [capture, setCapture] = useState<ReturnType<typeof pendingShare>>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const url = extractSharedUrl(params);
    // Preserve the share before AppShell requests authentication. Login returns here.
    if (url) setCapture(rememberShare(url));
    else if (!params.toString()) setCapture(pendingShare());
    else clearShare();
    window.history.replaceState(null, "", "/share/");
    setReady(true);
  }, []);
  return ready ? (
    <AppShell>
      <SaveShared capture={capture} />
    </AppShell>
  ) : (
    <p role="status">正在接收分享…</p>
  );
}
