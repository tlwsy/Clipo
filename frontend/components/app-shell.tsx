"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { api, ApiError, errorMessage, logout, type Schema } from "@/lib/api";
import { Brand, Icon } from "./icon";

const AccountContext = createContext<Schema["UserResponse"] | null>(null);

export function useAccount() {
  const user = useContext(AccountContext);
  if (!user) throw new Error("Account context is unavailable");
  return user;
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<Schema["UserResponse"] | null>(null);
  const [error, setError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    let active = true;
    const redirect = () => router.replace("/login/");
    window.addEventListener("clipo:unauthorized", redirect);
    async function load() {
      try {
        const meta = await api<Schema["VersionResponse"]>("/meta/version", {
          authenticated: false,
        });
        if (!active) return;
        if (!meta.setup_completed) {
          router.replace("/setup/");
          return;
        }
        const account = await api<Schema["UserResponse"]>("/auth/me");
        if (active) setUser(account);
      } catch (cause) {
        if (active && !(cause instanceof ApiError && cause.status === 401))
          setError(errorMessage(cause));
      }
    }
    void load();
    return () => {
      active = false;
      window.removeEventListener("clipo:unauthorized", redirect);
    };
  }, [router]);

  async function signOut() {
    setLoggingOut(true);
    try {
      await logout();
      router.replace("/login/");
    } catch (cause) {
      setError(errorMessage(cause));
      setLoggingOut(false);
    }
  }

  if (!user)
    return (
      <main className="loading-page">
        <Brand />
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button
              className="button secondary"
              onClick={() => location.reload()}
            >
              重新连接
            </button>
          </>
        ) : (
          <p role="status">正在打开你的空间…</p>
        )}
      </main>
    );

  return (
    <AccountContext.Provider value={user}>
      <div className="workspace">
        <aside className="sidebar">
          <Link href="/" aria-label="Clipo 首页">
            <Brand />
          </Link>
          <span className="sidebar-label">我的空间</span>
          <nav aria-label="主导航">
            <Link
              className={
                pathname === "/" || pathname.startsWith("/notes")
                  ? "nav-item active"
                  : "nav-item"
              }
              href="/"
            >
              <Icon name="grid" />
              全部笔记
            </Link>
            <Link
              className={
                pathname.startsWith("/jobs") ? "nav-item active" : "nav-item"
              }
              href="/jobs/"
            >
              <Icon name="clip" />
              保存队列
            </Link>
            <Link
              className={
                pathname.startsWith("/settings")
                  ? "nav-item active"
                  : "nav-item"
              }
              href="/settings/"
            >
              <Icon name="settings" />
              设置
            </Link>
          </nav>
          <div className="sidebar-bottom">
            <div className="private-note">
              <Icon name="lock" size={17} />
              <span>
                你的数据，你来保管<small>运行在自己的服务器上</small>
              </span>
            </div>
            <div className="account">
              <span className="avatar">
                {user.username.slice(0, 1).toUpperCase()}
              </span>
              <span className="account-name">
                {user.username}
                <small>{user.is_admin ? "管理员" : "成员"}</small>
              </span>
              <button
                className="icon-button"
                onClick={signOut}
                disabled={loggingOut}
                title="退出登录"
                aria-label="退出登录"
              >
                <Icon name="logout" size={18} />
              </button>
            </div>
          </div>
        </aside>
        <div className="main-area">
          <header className="topbar">
            <span>
              <span className="status-dot" /> 个人知识空间
            </span>
            <div className="topbar-actions">
              <span className="version-badge">v0.1.0 · 网页收藏</span>
              <button
                className="icon-button mobile-signout"
                onClick={signOut}
                disabled={loggingOut}
                aria-label="退出登录"
              >
                <Icon name="logout" size={17} />
              </button>
            </div>
          </header>
          <main className="page-content">
            {error && (
              <div className="notice error" role="alert">
                {error}
              </div>
            )}
            {children}
          </main>
          <footer className="workspace-footer">
            慢慢收集，让灵感生长。<span>Clipo · Self-hosted</span>
          </footer>
        </div>
      </div>
    </AccountContext.Provider>
  );
}
