// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";

import { afterLogin } from "@/lib/share";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { Icon } from "@/components/icon";
import { acceptSession, api, errorMessage, type Schema } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [register, setRegister] = useState(false);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Schema["VersionResponse"]>("/meta/version", { authenticated: false })
      .then((meta) => {
        if (!meta.setup_completed) {
          router.replace("/setup/");
          return;
        }
        setRegistrationOpen(meta.registration_open);
        setReady(true);
      })
      .catch((cause) => setError(errorMessage(cause)));
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const credentials: Schema["LoginRequest"] = {
      username: String(data.get("username")),
      password: String(data.get("password")),
    };
    try {
      const session = await api<Schema["SessionResponse"]>(
        register ? "/auth/register" : "/auth/login",
        {
          method: "POST",
          authenticated: false,
          body: JSON.stringify(
            register
              ? { ...credentials, email: data.get("email") }
              : credentials,
          ),
        },
      );
      acceptSession(session);
      router.replace(afterLogin());
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <span className="eyebrow">
        {register ? "MAKE YOURSELF AT HOME" : "WELCOME BACK"}
      </span>
      <h2>{register ? "创建你的账号" : "欢迎回到 Clipo"}</h2>
      <p className="form-intro">
        {register
          ? "给你的灵感，一个属于自己的空间。"
          : "登录，继续积累你的灵感与发现。"}
      </p>
      <form onSubmit={submit}>
        <label>
          用户名
          <input
            name="username"
            autoComplete="username"
            minLength={3}
            maxLength={64}
            required
            placeholder="输入你的用户名"
          />
        </label>
        {register && (
          <label>
            邮箱
            <input
              name="email"
              type="email"
              autoComplete="email"
              required
              placeholder="you@example.com"
            />
          </label>
        )}
        <label>
          密码
          <input
            name="password"
            type="password"
            autoComplete={register ? "new-password" : "current-password"}
            minLength={register ? 10 : 1}
            maxLength={128}
            required
            placeholder={register ? "至少 10 个字符" : "输入你的密码"}
          />
        </label>
        {error && (
          <div className="notice error" role="alert">
            {error}
            {!ready && (
              <button
                type="button"
                className="inline-button"
                onClick={() => location.reload()}
              >
                重新连接
              </button>
            )}
          </div>
        )}
        <button className="button full-width" disabled={busy || !ready}>
          {busy ? "请稍候…" : register ? "创建账号" : "登录你的空间"}
          <Icon name="arrow" size={18} />
        </button>
      </form>
      {registrationOpen && (
        <button
          className="switch-auth"
          onClick={() => {
            setRegister(!register);
            setError("");
          }}
        >
          {register ? "已有账号？返回登录" : "还没有账号？创建一个"}
        </button>
      )}
      <div className="form-note">
        <Icon name="lock" size={14} /> 连接你的自托管实例
      </div>
    </AuthFrame>
  );
}
