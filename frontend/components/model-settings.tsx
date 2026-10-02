// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "@/components/icon";
import { api, errorMessage, type Schema } from "@/lib/api";
import { modelProviders, providerForUrl } from "@/lib/model-providers";

export function ModelSettings({ initial }: { initial: Schema["LlmResponse"] }) {
  const [current, setCurrent] = useState(initial);
  const [baseUrl, setBaseUrl] = useState(initial.base_url);
  const [model, setModel] = useState(initial.model);
  const [budget, setBudget] = useState(initial.text_token_budget);
  const [maxComments, setMaxComments] = useState(initial.max_comments);
  const [commentThreshold, setCommentThreshold] = useState(
    initial.comment_score_threshold,
  );
  const [key, setKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelsMessage, setModelsMessage] = useState("");
  const [modelsError, setModelsError] = useState("");
  const discovery = useRef<AbortController | null>(null);
  const overridden = (field: string) =>
    current.overridden_fields.includes(field);
  const addressChanged =
    baseUrl.replace(/\/+$/, "") !== current.base_url.replace(/\/+$/, "");

  useEffect(() => () => discovery.current?.abort(), []);

  function resetModels() {
    discovery.current?.abort();
    discovery.current = null;
    setLoadingModels(false);
    setModels([]);
    setModelsMessage("");
    setModelsError("");
  }

  function changeAddress(value: string) {
    resetModels();
    setBaseUrl(value);
    setKey("");
    setClearKey(false);
    setMessage("");
    if (!overridden("model")) setModel("");
  }

  async function fetchModels() {
    resetModels();
    const controller = new AbortController();
    discovery.current = controller;
    setLoadingModels(true);
    const timeout = setTimeout(() => controller.abort(), 25000);
    const payload: Schema["LlmModelsRequest"] = {};
    if (!overridden("base_url")) payload.base_url = baseUrl;
    if (!overridden("api_key") && (key || clearKey))
      payload.api_key = clearKey ? null : key;
    try {
      const result = await api<Schema["LlmModelsResponse"]>(
        "/settings/llm/models",
        {
          method: "POST",
          body: JSON.stringify(payload),
          signal: controller.signal,
        },
      );
      if (discovery.current !== controller) return;
      setModels(result.models);
      setModelsMessage(
        result.models.length
          ? `已获取 ${result.models.length} 个模型，请选择支持文本对话的模型。`
          : "服务返回了空列表，请手动填写模型名称。",
      );
    } catch (cause) {
      if (discovery.current === controller)
        setModelsError(
          controller.signal.aborted
            ? "获取超时，请重试或手动填写模型名称。"
            : errorMessage(cause),
        );
    } finally {
      clearTimeout(timeout);
      if (discovery.current === controller) {
        discovery.current = null;
        setLoadingModels(false);
      }
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      addressChanged &&
      current.api_key_set &&
      ((!key && !clearKey) || overridden("api_key"))
    ) {
      setError(
        "更换服务地址时，请填写新服务的 API Key 或清除旧密钥；部署密钥需由管理员修改。",
      );
      return;
    }
    resetModels();
    setBusy(true);
    setMessage("");
    setError("");
    const llm: Schema["LlmUpdate"] = {};
    llm.text_token_budget = budget;
    llm.max_comments = maxComments;
    llm.comment_score_threshold = commentThreshold;
    if (!overridden("base_url")) llm.base_url = baseUrl;
    if (!overridden("model")) llm.model = model;
    if (!overridden("api_key") && (clearKey || key))
      llm.api_key = clearKey ? null : key;
    try {
      const result = await api<Schema["SettingsResponse"]>("/settings", {
        method: "PUT",
        body: JSON.stringify({ llm } satisfies Schema["SettingsUpdate"]),
      });
      setCurrent(result.llm);
      setBaseUrl(result.llm.base_url);
      setModel(result.llm.model);
      setBudget(result.llm.text_token_budget);
      setMaxComments(result.llm.max_comments);
      setCommentThreshold(result.llm.comment_score_threshold);
      setKey("");
      setClearKey(false);
      setMessage("模型配置已保存");
      window.dispatchEvent(new Event("clipo:model-settings"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="settings-card" id="llm">
      <div className="card-heading">
        <span className="feature-icon">
          <Icon name="spark" />
        </span>
        <div>
          <h2>AI 模型</h2>
          <p>连接你选择的 OpenAI 兼容服务</p>
        </div>
        <span className={current.api_key_set ? "pill" : "subtle-badge"}>
          {current.api_key_set ? "已配置密钥" : "待配置"}
        </span>
      </div>
      <form onSubmit={save}>
        {current.overridden_fields.length > 0 && (
          <div className="notice">部分配置由部署环境管理，已锁定对应字段。</div>
        )}
        <label>
          服务商预设
          <select
            value={providerForUrl(baseUrl)}
            disabled={overridden("base_url") || busy}
            onChange={(event) =>
              changeAddress(
                modelProviders.find(
                  (provider) => provider.id === event.target.value,
                )?.baseUrl ?? "",
              )
            }
          >
            {modelProviders.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
              </option>
            ))}
            <option value="custom">自定义 OpenAI 兼容服务</option>
          </select>
          <small>
            选择后填入服务地址；其他地域、专属端点或中转服务可自行修改。
          </small>
        </label>
        <label>
          Base URL
          <input
            type="url"
            required
            value={baseUrl}
            onChange={(e) => changeAddress(e.target.value)}
            disabled={overridden("base_url") || busy}
          />
          <small>例如 https://api.deepseek.com/v1</small>
        </label>
        <label>
          API Key
          <input
            type="password"
            maxLength={4096}
            value={key}
            onChange={(e) => {
              resetModels();
              setKey(e.target.value);
            }}
            disabled={overridden("api_key") || clearKey || busy}
            autoComplete="off"
            placeholder={
              current.api_key_set && !addressChanged
                ? "已保存，留空保留现有密钥"
                : "填入模型服务的 API Key"
            }
          />
          <small>密钥加密存储，保存后不再显示原文。</small>
        </label>
        {current.api_key_set && !overridden("api_key") && (
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={clearKey}
              disabled={busy}
              onChange={(e) => {
                resetModels();
                setClearKey(e.target.checked);
              }}
            />{" "}
            清除已保存的密钥
          </label>
        )}
        {addressChanged && current.api_key_set && (
          <p className="notice">
            服务地址已更改，请填写对应的新密钥或清除旧密钥后保存。
          </p>
        )}
        <div className="model-discovery">
          <button
            type="button"
            className="button secondary small"
            disabled={
              busy ||
              loadingModels ||
              overridden("model") ||
              !baseUrl ||
              clearKey ||
              (!key && (!current.api_key_set || addressChanged))
            }
            onClick={fetchModels}
          >
            {loadingModels ? "正在获取…" : "获取模型列表"}
          </button>
          <small>
            使用上方配置获取，无需先保存。暂不支持的服务可手动填写。
          </small>
        </div>
        {modelsError && (
          <div className="notice error" role="alert">
            {modelsError}
          </div>
        )}
        {modelsMessage && (
          <p className="notice" role="status">
            {modelsMessage}
          </p>
        )}
        {models.length > 0 && (
          <label>
            可用模型
            <select
              value={models.includes(model) ? model : ""}
              disabled={overridden("model") || busy}
              onChange={(event) => {
                if (event.target.value) setModel(event.target.value);
              }}
            >
              <option value="">请选择模型，或在下方手动填写</option>
              {models.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          模型名称
          <input
            required
            aria-label="模型名称"
            aria-describedby="model-name-help"
            maxLength={100}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={overridden("model") || busy}
            placeholder="选择上方模型或填写模型 ID"
          />
          <small id="model-name-help">
            模型列表由服务商提供；是否支持摘要所需的对话能力，以该模型实际接口为准。
          </small>
        </label>
        <label>
          正文 token 预算
          <input
            type="number"
            required
            min={100}
            max={100000}
            value={budget}
            onChange={(event) => setBudget(Number(event.target.value))}
          />
          <small>超出预算的正文仅截断后送给模型，保存的原文保持完整。</small>
        </label>
        <div className="notice">
          配置生效后，新保存的网页会自动生成摘要与要点。模型暂时不可用时，仍会为你保存原文和已采集评论。
        </div>
        <label>
          候选评论上限
          <input
            type="number"
            required
            min={1}
            max={100}
            step={1}
            value={maxComments}
            onChange={(event) => setMaxComments(Number(event.target.value))}
          />
          <small>
            在已采集的评论中按点赞、回复数排序并去重，过滤过短和纯表情评论后，最多选取这些评论评分。长评论可能进一步限量，已采集评论全部保留。
          </small>
        </label>
        <label>
          高价值评论阈值
          <input
            type="number"
            required
            min={0}
            max={1}
            step="any"
            value={commentThreshold}
            onChange={(event) =>
              setCommentThreshold(Number(event.target.value))
            }
          />
          <small>
            评分范围为
            0–1，达到阈值即标记为高价值。设置仅对之后的采集生效，已有笔记保留原来的评分。
          </small>
        </label>
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        {message && (
          <div className="notice success" role="status">
            {message}
          </div>
        )}
        <div className="form-bottom">
          <span>
            <Icon name="lock" size={14} /> 仅供当前账号使用
          </span>
          <button className="button" disabled={busy}>
            {busy ? "保存中…" : "保存配置"}
          </button>
        </div>
      </form>
    </section>
  );
}
