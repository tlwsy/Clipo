// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useState } from "react";
import {
  readingThemes,
  readingVariables,
  resolvedReadingStyle,
  themeLabels,
  type ReadingStyle,
  type StylePatch,
} from "@/lib/reading";
import { CollectionDialog } from "./collection-dialog";

export function ReadingStyleSettings({
  preferences,
  overrides,
  busy,
  error,
  onSave,
  onReset,
  onClose,
}: {
  preferences?: ReadingStyle;
  overrides: StylePatch;
  busy: boolean;
  error: string;
  onSave: (patch: StylePatch, global: boolean) => Promise<void>;
  onReset: () => Promise<void>;
  onClose: () => void;
}) {
  const [global, setGlobal] = useState(false);
  const [patch, setPatch] = useState<StylePatch>({});
  const initial = resolvedReadingStyle(preferences, global ? {} : overrides);
  const draft = resolvedReadingStyle(initial, patch);
  function update<K extends keyof StylePatch>(key: K, value: StylePatch[K]) {
    setPatch((current) => ({ ...current, [key]: value }));
  }
  return (
    <CollectionDialog title="阅读样式" onClose={onClose} busy={busy}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void onSave(patch, global).catch(() => undefined);
        }}
      >
        <label>
          应用范围
          <select
            value={global ? "global" : "note"}
            disabled={busy}
            onChange={(event) => {
              setGlobal(event.target.value === "global");
              setPatch({});
            }}
          >
            <option value="note">仅本文</option>
            <option value="global">所有笔记</option>
          </select>
        </label>
        <div className="reading-themes" role="group" aria-label="预设主题">
          {Object.entries(themeLabels).map(([key, label]) => (
            <button
              type="button"
              key={key}
              aria-pressed={draft.theme === key}
              disabled={busy}
              style={{
                backgroundColor:
                  readingThemes[key as ReadingStyle["theme"]].background_color,
                color: readingThemes[key as ReadingStyle["theme"]].text_color,
              }}
              onClick={() => setPatch({ theme: key as ReadingStyle["theme"] })}
            >
              {label}
            </button>
          ))}
        </div>
        <details className="reading-advanced">
          <summary>高级调整</summary>
          <label>
            字体
            <select
              value={draft.font_family}
              disabled={busy}
              onChange={(event) =>
                update(
                  "font_family",
                  event.target.value as ReadingStyle["font_family"],
                )
              }
            >
              <option value="system-ui">系统字体</option>
              <option value="serif">衬线字体</option>
              <option value="sans-serif">无衬线字体</option>
            </select>
          </label>
          <label>
            字号（{draft.font_size}px）
            <input
              type="range"
              min={14}
              max={24}
              value={draft.font_size}
              disabled={busy}
              onChange={(event) =>
                update("font_size", Number(event.target.value))
              }
            />
          </label>
          <label>
            字重
            <select
              value={draft.font_weight}
              disabled={busy}
              onChange={(event) =>
                update(
                  "font_weight",
                  Number(event.target.value) as ReadingStyle["font_weight"],
                )
              }
            >
              {[400, 500, 600, 700].map((weight) => (
                <option key={weight} value={weight}>
                  {weight}
                </option>
              ))}
            </select>
          </label>
          <label>
            行距（{draft.line_height}）
            <input
              type="range"
              min={1.2}
              max={2}
              step={0.1}
              value={draft.line_height}
              disabled={busy}
              onChange={(event) =>
                update("line_height", Number(event.target.value))
              }
            />
          </label>
          <label>
            段距（{draft.paragraph_spacing}px）
            <input
              type="range"
              min={0}
              max={40}
              value={draft.paragraph_spacing}
              disabled={busy}
              onChange={(event) =>
                update("paragraph_spacing", Number(event.target.value))
              }
            />
          </label>
          <label>
            内容宽度（{draft.content_width}px）
            <input
              type="range"
              min={600}
              max={900}
              step={10}
              value={draft.content_width}
              disabled={busy}
              onChange={(event) =>
                update("content_width", Number(event.target.value))
              }
            />
          </label>
          <label>
            对齐方式
            <select
              value={draft.text_align}
              disabled={busy}
              onChange={(event) =>
                update(
                  "text_align",
                  event.target.value as ReadingStyle["text_align"],
                )
              }
            >
              <option value="left">左对齐</option>
              <option value="justify">两端对齐</option>
            </select>
          </label>
          <div className="reading-colors">
            <label>
              背景颜色
              <input
                type="color"
                value={draft.background_color}
                disabled={busy}
                onChange={(event) =>
                  update("background_color", event.target.value)
                }
              />
            </label>
            <label>
              文字颜色
              <input
                type="color"
                value={draft.text_color}
                disabled={busy}
                onChange={(event) => update("text_color", event.target.value)}
              />
            </label>
          </div>
        </details>
        <div
          className="reading-surface reading-preview"
          style={readingVariables(draft)}
        >
          <div className="article-content">
            <p>阅读预览：让值得记住的内容，成为自己的知识。</p>
          </div>
        </div>
        <p className="muted">
          样式用于原始正文。已有本文覆盖的笔记会保留自己的样式；切换主题会重置当前范围的旧调整。
        </p>
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        <div className="annotation-actions">
          <button
            className="button small"
            disabled={busy || !Object.keys(patch).length}
          >
            {busy ? "保存中…" : "保存样式"}
          </button>
          {!global && (
            <button
              type="button"
              className="inline-button"
              disabled={busy}
              onClick={() => void onReset().catch(() => undefined)}
            >
              本文跟随全局
            </button>
          )}
        </div>
      </form>
    </CollectionDialog>
  );
}
