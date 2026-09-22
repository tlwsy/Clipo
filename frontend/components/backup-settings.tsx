// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { api, errorMessage, type Schema } from "@/lib/api";
import { captureKey } from "@/lib/share";

const statusLabels = {
  queued: "等待处理",
  running: "处理中",
  retrying: "等待重试",
  success: "已完成",
  failed: "失败",
};
const kindLabels = { export: "导出", import: "导入", backup: "备份" };

export function BackupSettings() {
  const [config, setConfig] = useState<Schema["BackupSettingsResponse"] | null>(
    null,
  );
  const [jobs, setJobs] = useState<Schema["BackupJobResponse"][]>([]);
  const [accessKey, setAccessKey] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const refresh = useCallback(async () => {
    setJobs(await api<Schema["BackupJobResponse"][]>("/backups"));
  }, []);

  useEffect(() => {
    let active = true;
    api<Schema["BackupSettingsResponse"]>("/backups/settings")
      .then((value) => {
        if (active) setConfig(value);
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      });
    const poll = () => {
      api<Schema["BackupJobResponse"][]>("/backups")
        .then((value) => {
          if (active) setJobs(value);
        })
        .catch((cause) => {
          if (active) setError(errorMessage(cause));
        });
    };
    poll();
    const timer = setInterval(poll, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config) return;
    await perform(async () => {
      const body: Schema["BackupSettingsUpdate"] = {
        clear_credentials: false,
        target: config.target,
        schedule: config.schedule,
        endpoint: config.endpoint,
        bucket: config.bucket,
        region: config.region,
        prefix: config.prefix,
        username: config.username,
        ...(accessKey ? { access_key: accessKey } : {}),
        ...(secret ? { secret } : {}),
      };
      setConfig(
        await api<Schema["BackupSettingsResponse"]>("/backups/settings", {
          method: "PUT",
          body: JSON.stringify(body),
        }),
      );
      setAccessKey("");
      setSecret("");
      setMessage("备份配置已保存");
    });
  }

  async function start(path: string) {
    await perform(async () => {
      await api<Schema["BackupJobResponse"]>(path, {
        method: "POST",
        body: JSON.stringify({ request_key: captureKey() }),
      });
      await refresh();
      setMessage("任务已提交，可在下方查看结果");
    });
  }

  async function restore() {
    if (!file) return;
    if (file.size > 100 * 1024 * 1024) {
      setError("导入文件上限为 100 MiB");
      return;
    }
    await perform(async () => {
      await api<Schema["BackupJobResponse"]>("/backups/imports", {
        method: "POST",
        body: file,
      });
      setFile(null);
      if (input.current) input.current.value = "";
      await refresh();
      setMessage("导入任务已提交，完成后刷新笔记列表");
    });
  }

  async function download(id: string) {
    await perform(async () => {
      const blob = await api<Blob>(`/backups/${id}/download`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `clipo-${id}.zip`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    });
  }

  return (
    <section className="settings-card" id="backups">
      <div className="card-heading">
        <div>
          <h2>备份与恢复</h2>
          <p>把笔记库保存到自己选择的地方</p>
        </div>
      </div>
      <p className="section-description">
        导出包含原文、摘要、评论、标签、收藏与媒体链接。账号密码和服务密钥不在其中；图片仍为外链。
      </p>
      <div className="token-actions">
        <button
          className="button secondary"
          disabled={busy}
          onClick={() => start("/backups/exports")}
        >
          导出 JSON 与 Markdown
        </button>
      </div>
      <label>
        导入 library.json
        <input
          ref={input}
          type="file"
          accept=".json,application/json"
          disabled={busy}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <p className="section-description">
        选择解压后的 JSON，最多 100
        MiB。导入会追加到当前账号；相同文件重复提交不会重复添加。完整校验失败不会写入笔记。
      </p>
      <button
        className="button secondary"
        disabled={busy || !file}
        onClick={restore}
      >
        确认追加导入
      </button>
      {config && (
        <form onSubmit={save}>
          <label>
            备份目标
            <select
              value={config.target}
              onChange={(e) =>
                setConfig({
                  ...config,
                  target: e.target
                    .value as Schema["BackupSettingsResponse"]["target"],
                })
              }
            >
              <option value="none">关闭自动备份</option>
              <option value="local">服务器本地目录</option>
              <option value="s3">S3 兼容存储</option>
              <option value="webdav">WebDAV</option>
            </select>
          </label>
          {config.target !== "none" && (
            <>
              <label>
                备份计划
                <input
                  value={config.schedule}
                  onChange={(e) =>
                    setConfig({ ...config, schedule: e.target.value })
                  }
                  placeholder="0 4 * * *"
                  maxLength={100}
                />
                <small>
                  五段 Cron，{config.timezone} 时区。例如 0 4 * * * 为每日
                  04:00；留空仅手动备份。
                </small>
              </label>
              {config.target === "local" ? (
                <p className="section-description">
                  保存到管理员设置的目录，按账号隔离，保留最近{" "}
                  {config.local_keep} 份。
                </p>
              ) : (
                <>
                  <label>
                    服务地址
                    <input
                      type="url"
                      required
                      value={config.endpoint}
                      onChange={(e) =>
                        setConfig({ ...config, endpoint: e.target.value })
                      }
                      placeholder="https://storage.example.com"
                    />
                  </label>
                  <label>
                    目录前缀
                    <input
                      value={config.prefix}
                      onChange={(e) =>
                        setConfig({ ...config, prefix: e.target.value })
                      }
                      maxLength={200}
                    />
                    <small>
                      WebDAV
                      中该目录须已存在；内网地址需管理员配置允许的服务器。
                    </small>
                  </label>
                  {config.target === "s3" ? (
                    <>
                      <label>
                        存储桶
                        <input
                          required
                          value={config.bucket}
                          onChange={(e) =>
                            setConfig({ ...config, bucket: e.target.value })
                          }
                          maxLength={63}
                        />
                      </label>
                      <label>
                        区域
                        <input
                          required
                          value={config.region}
                          onChange={(e) =>
                            setConfig({ ...config, region: e.target.value })
                          }
                          maxLength={100}
                        />
                      </label>
                      <label>
                        Access Key
                        <input
                          type="password"
                          autoComplete="off"
                          value={accessKey}
                          onChange={(e) => setAccessKey(e.target.value)}
                          placeholder={
                            config.access_key_set
                              ? "已保存，留空保留"
                              : "填写 Access Key"
                          }
                        />
                      </label>
                    </>
                  ) : (
                    <label>
                      用户名
                      <input
                        required
                        value={config.username}
                        onChange={(e) =>
                          setConfig({ ...config, username: e.target.value })
                        }
                        maxLength={200}
                      />
                    </label>
                  )}
                  <label>
                    {config.target === "s3" ? "Secret Key" : "应用密码"}
                    <input
                      type="password"
                      autoComplete="off"
                      value={secret}
                      onChange={(e) => setSecret(e.target.value)}
                      placeholder={
                        config.secret_set
                          ? "已保存，留空保留"
                          : "填写密钥或应用密码"
                      }
                    />
                  </label>
                  <small>
                    凭据加密保存。更换目标、服务地址或用户名时请重新填写凭据；远端保留周期在存储服务中设置。
                  </small>
                </>
              )}
            </>
          )}
          <div className="form-bottom">
            <button className="button" disabled={busy}>
              保存备份配置
            </button>
            <button
              type="button"
              className="button secondary"
              disabled={busy || config.target === "none"}
              onClick={() => start("/backups/run")}
            >
              立即备份
            </button>
          </div>
          <small>
            立即备份使用已保存的配置。下载文件保留{" "}
            {config.download_retention_days} 天。
          </small>
        </form>
      )}
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
      {jobs.length > 0 && (
        <ul className="token-list" aria-label="备份任务">
          {jobs.map((job) => (
            <li key={job.id}>
              <div>
                <strong>
                  {kindLabels[job.kind]} · {statusLabels[job.status]}
                </strong>
                <small>
                  {new Date(job.created_at).toLocaleString("zh-CN")}
                  {job.note_count !== null ? ` · ${job.note_count} 篇笔记` : ""}
                </small>
                {job.last_error && <p>{job.last_error}</p>}
              </div>
              <div className="token-actions">
                {job.status === "success" && job.kind !== "import" && (
                  <button
                    className="inline-button"
                    disabled={busy}
                    onClick={() => download(job.id)}
                  >
                    下载 ZIP
                  </button>
                )}
                {job.status === "failed" && (
                  <button
                    className="inline-button"
                    disabled={busy}
                    onClick={() => start(`/backups/${job.id}/retry`)}
                  >
                    重试
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
