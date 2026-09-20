"use client";

import { afterLogin } from "@/lib/share";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { Icon } from "@/components/icon";
import {
  acceptSession,
  api,
  ApiError,
  errorMessage,
  type Schema,
} from "@/lib/api";

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [configureLlm, setConfigureLlm] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const [account, setAccount] = useState({
    username: "",
    email: "",
    password: "",
  });
  const [llm, setLlm] = useState({
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
    api_key: "",
  });

  useEffect(() => {
    api<Schema["VersionResponse"]>("/meta/version", { authenticated: false })
      .then((meta) => {
        if (meta.setup_completed) router.replace("/login/");
        else setReady(true);
      })
      .catch((cause) => setError(errorMessage(cause)));
  }, [router]);

  useEffect(() => {
    const field = Object.keys(fieldErrors)[0]?.replace(/^body\./, "");
    const input = field ? formRef.current?.elements.namedItem(field) : null;
    if (input instanceof HTMLInputElement) input.focus();
  }, [fieldErrors, step]);

  function showError(cause: unknown) {
    setError(errorMessage(cause));
    if (cause instanceof ApiError) {
      const fields = cause.detail.fields ?? [];
      setFieldErrors(
        Object.fromEntries(fields.map((field) => [field.field, field.message])),
      );
      if (
        fields.some((field) =>
          ["body.username", "body.email", "body.password"].includes(
            field.field,
          ),
        )
      ) {
        setStep(1);
      }
    }
  }

  async function complete(includeLlm: boolean) {
    setBusy(true);
    setError("");
    setFieldErrors({});
    const payload: Schema["SetupRequest"] = {
      ...account,
      ...(includeLlm ? { llm } : {}),
    };
    try {
      const session = await api<Schema["SessionResponse"]>("/setup", {
        method: "POST",
        authenticated: false,
        body: JSON.stringify(payload),
      });
      acceptSession(session);
      router.replace(afterLogin());
    } catch (cause) {
      showError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    if (step === 2) {
      await complete(configureLlm);
      return;
    }
    setBusy(true);
    try {
      await api<void>("/setup/validate", {
        method: "POST",
        authenticated: false,
        body: JSON.stringify(account satisfies Schema["RegisterRequest"]),
      });
      setStep(2);
    } catch (cause) {
      showError(cause);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <div
        className="setup-progress"
        aria-label={`设置进度：第 ${step} 步，共 2 步`}
      >
        <span className={step === 1 ? "current" : "done"}>01 创建账号</span>
        <span className="progress-line" />
        <span className={step === 2 ? "current" : ""}>02 AI 配置（可选）</span>
      </div>
      <h2>{step === 1 ? "一个全新的开始" : "AI 可以稍后再配置"}</h2>
      <p className="form-intro">
        {step === 1
          ? "欢迎使用 Clipo。先创建你的管理员账号。"
          : "账号信息已通过检查。直接创建空间，之后随时可以在设置中添加 AI 服务。"}
      </p>
      <form ref={formRef} onSubmit={submit}>
        <fieldset className="setup-fields" disabled={busy || !ready}>
          {step === 1 ? (
            <>
              <label>
                用户名
                <input
                  value={account.username}
                  onChange={(e) =>
                    setAccount({ ...account, username: e.target.value })
                  }
                  name="username"
                  aria-invalid={Boolean(fieldErrors["body.username"])}
                  aria-describedby={
                    fieldErrors["body.username"] ? "username-error" : undefined
                  }
                  autoComplete="username"
                  minLength={3}
                  maxLength={64}
                  required
                  placeholder="给自己起个名字"
                />
                <small>3–64 个字符，可使用文字、数字、下划线和短横线</small>
                {fieldErrors["body.username"] && (
                  <small className="field-error" id="username-error">
                    {fieldErrors["body.username"]}
                  </small>
                )}
              </label>
              <label>
                邮箱
                <input
                  value={account.email}
                  onChange={(e) =>
                    setAccount({ ...account, email: e.target.value })
                  }
                  name="email"
                  aria-invalid={Boolean(fieldErrors["body.email"])}
                  aria-describedby={
                    fieldErrors["body.email"] ? "email-error" : undefined
                  }
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="you@example.com"
                />
                {fieldErrors["body.email"] && (
                  <small className="field-error" id="email-error">
                    {fieldErrors["body.email"]}
                  </small>
                )}
              </label>
              <label>
                密码
                <input
                  value={account.password}
                  onChange={(e) =>
                    setAccount({ ...account, password: e.target.value })
                  }
                  name="password"
                  aria-invalid={Boolean(fieldErrors["body.password"])}
                  aria-describedby={
                    fieldErrors["body.password"] ? "password-error" : undefined
                  }
                  type="password"
                  autoComplete="new-password"
                  minLength={10}
                  maxLength={128}
                  required
                  placeholder="至少 10 个字符"
                />
                {fieldErrors["body.password"] && (
                  <small className="field-error" id="password-error">
                    {fieldErrors["body.password"]}
                  </small>
                )}
              </label>
            </>
          ) : (
            <>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={configureLlm}
                  onChange={(event) => {
                    setConfigureLlm(event.target.checked);
                    setError("");
                    setFieldErrors({});
                  }}
                />
                现在配置 AI（可选）
              </label>
              {configureLlm && (
                <>
                  <label>
                    Base URL
                    <input
                      type="url"
                      name="llm.base_url"
                      aria-invalid={Boolean(fieldErrors["body.llm.base_url"])}
                      aria-describedby={
                        fieldErrors["body.llm.base_url"]
                          ? "llm-url-error"
                          : undefined
                      }
                      value={llm.base_url}
                      onChange={(e) =>
                        setLlm({ ...llm, base_url: e.target.value })
                      }
                      required
                    />
                    <small>支持通义千问、DeepSeek 等 OpenAI 兼容服务</small>
                    {fieldErrors["body.llm.base_url"] && (
                      <small className="field-error" id="llm-url-error">
                        {fieldErrors["body.llm.base_url"]}
                      </small>
                    )}
                  </label>
                  <label>
                    模型名称
                    <input
                      name="llm.model"
                      aria-invalid={Boolean(fieldErrors["body.llm.model"])}
                      aria-describedby={
                        fieldErrors["body.llm.model"]
                          ? "llm-model-error"
                          : undefined
                      }
                      value={llm.model}
                      maxLength={100}
                      onChange={(e) =>
                        setLlm({ ...llm, model: e.target.value })
                      }
                      required
                      placeholder="qwen-plus"
                    />
                    {fieldErrors["body.llm.model"] && (
                      <small className="field-error" id="llm-model-error">
                        {fieldErrors["body.llm.model"]}
                      </small>
                    )}
                  </label>
                  <label>
                    API Key
                    <input
                      type="password"
                      name="llm.api_key"
                      value={llm.api_key}
                      onChange={(e) =>
                        setLlm({ ...llm, api_key: e.target.value })
                      }
                      autoComplete="off"
                      maxLength={4096}
                      placeholder="sk-…（可选）"
                    />
                    <small>密钥加密保存，模型调用费用由你的服务商收取</small>
                  </label>
                </>
              )}
            </>
          )}
        </fieldset>
        {error && (
          <div className="notice error" role="alert">
            {error}
            {!ready && (
              <button
                className="inline-button"
                type="button"
                onClick={() => location.reload()}
              >
                重新连接
              </button>
            )}
          </div>
        )}
        <button className="button full-width" disabled={busy || !ready}>
          {busy
            ? step === 1
              ? "正在检查账号…"
              : "正在创建空间…"
            : step === 1
              ? "下一步"
              : configureLlm
                ? "保存 AI 配置并创建空间"
                : "跳过 AI，创建空间"}
          <Icon name="arrow" size={18} />
        </button>
        {step === 2 && (
          <div className="setup-actions">
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setStep(1);
                setError("");
                setFieldErrors({});
              }}
            >
              返回上一步
            </button>
            {configureLlm && (
              <button
                type="button"
                disabled={busy || !ready}
                onClick={() => complete(false)}
              >
                不保存 AI 配置，直接创建
              </button>
            )}
          </div>
        )}
      </form>
      <div className="form-note">
        <Icon name="lock" size={14} /> 账号与配置只保存在你的服务器上
      </div>
    </AuthFrame>
  );
}
