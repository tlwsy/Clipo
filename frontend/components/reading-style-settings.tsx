// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useId, useState, type CSSProperties } from "react";
import Markdown from "react-markdown";
import {
  readingFonts,
  readingPalettes,
  readingThemes,
  readingVariables,
  resolvedReadingStyle,
  themeLabels,
  type ReadingStyle,
  type StylePatch,
} from "@/lib/reading";
import { CollectionDialog } from "./collection-dialog";

const tabs = ["主题", "字体", "排版"] as const;
const fontOptions = [
  { value: "system-ui", label: "系统字体" },
  { value: "serif", label: "宋体 / 衬线" },
  { value: "sans-serif", label: "无衬线" },
] as const;

function StyleChoices<T extends string | number>({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  disabled: boolean;
  onChange: (value: T) => void;
}) {
  return (
    <div className="style-field">
      <span className="style-label">{label}</span>
      <div className="style-segments" role="group" aria-label={label}>
        {options.map((option) => (
          <button
            type="button"
            key={option.value}
            aria-pressed={value === option.value}
            disabled={disabled}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function StyleSlider({
  label,
  value,
  unit = "",
  min,
  max,
  step = 1,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  unit?: string;
  min: number;
  max: number;
  step?: number;
  disabled: boolean;
  onChange: (value: number) => void;
}) {
  const id = useId();
  return (
    <div className="style-field">
      <label className="style-label" htmlFor={id}>
        {label}
        <output htmlFor={id}>
          {value}
          {unit}
        </output>
      </label>
      <input
        id={id}
        className="style-slider"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        style={
          {
            "--slider-fill": `${((value - min) / (max - min)) * 100}%`,
          } as CSSProperties
        }
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

export function ReadingStyleSettings({
  preferences,
  overrides,
  preview,
  busy,
  error,
  onSave,
  onReset,
  onClose,
}: {
  preferences?: ReadingStyle;
  overrides: StylePatch;
  preview?: { title: string; text: string; summary: string };
  busy: boolean;
  error: string;
  onSave: (patch: StylePatch, global: boolean) => Promise<void>;
  onReset: () => Promise<void>;
  onClose: () => void;
}) {
  const id = useId();
  const [scope, setScope] = useState<"note" | "global">("note");
  const [patches, setPatches] = useState<Record<typeof scope, StylePatch>>({
    note: {},
    global: {},
  });
  const [tab, setTab] = useState(0);
  const patch = patches[scope];
  const initial = resolvedReadingStyle(
    preferences,
    scope === "global" ? {} : overrides,
  );
  const draft = resolvedReadingStyle(initial, patch);
  const paragraphs = (
    preview?.text ||
    "让值得记住的内容，成为自己的知识。\n\n放慢一点，在字里行间发现新的想法。选择适合自己的字体、留白与颜色，让每一次阅读都更自在。"
  )
    .slice(0, 900)
    .split(/\n+/)
    .filter(Boolean)
    .slice(0, 5);
  function replacePatch(next: StylePatch) {
    setPatches((current) => ({ ...current, [scope]: next }));
  }
  function update<K extends keyof StylePatch>(key: K, value: StylePatch[K]) {
    setPatches((current) => ({
      ...current,
      [scope]: { ...current[scope], [key]: value },
    }));
  }
  return (
    <CollectionDialog
      title="阅读样式"
      className="reading-style-dialog"
      onClose={onClose}
      busy={busy}
    >
      <p className="style-intro">为每一次阅读，找到舒服的模样。</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void onSave(patch, scope === "global").catch(() => undefined);
        }}
      >
        <div className="style-workspace">
          <div className="style-preview-stage">
            <div className="style-preview-label">
              <span>效果预览</span>
              <span>标题 · 摘要 · 正文 · 评论</span>
            </div>
            <div
              className="style-preview-paper reader-styled"
              style={readingVariables(draft)}
              tabIndex={0}
              role="region"
              aria-label="阅读效果预览"
            >
              <div
                className="style-preview-content"
                style={
                  {
                    "--preview-width": `${(draft.content_width / 900) * 100}%`,
                  } as CSSProperties
                }
              >
                <span className="eyebrow">CLIPO · 阅读时光</span>
                <h3 className="style-preview-title">
                  {preview?.title || "把好想法，留给未来的自己"}
                </h3>
                {preview?.summary && (
                  <div className="style-preview-summary">
                    <span className="pill">AI 整理</span>
                    <div className="markdown">
                      <Markdown
                        skipHtml
                        disallowedElements={["img", "a"]}
                        unwrapDisallowed
                      >
                        {preview.summary.slice(0, 300)}
                      </Markdown>
                    </div>
                  </div>
                )}
                <div className="article-content">
                  {paragraphs.map((paragraph, index) => (
                    <p key={index}>{paragraph}</p>
                  ))}
                </div>
              </div>
            </div>
            <p className="style-preview-caption">
              调整即时预览，保存后应用到阅读页
            </p>
          </div>
          <div className="style-controls">
            <div className="style-tabs" role="tablist" aria-label="样式分类">
              {tabs.map((label, index) => (
                <button
                  type="button"
                  role="tab"
                  key={label}
                  id={`${id}-tab-${index}`}
                  aria-controls={`${id}-panel-${index}`}
                  aria-selected={tab === index}
                  tabIndex={tab === index ? 0 : -1}
                  onClick={() => setTab(index)}
                  onKeyDown={(event) => {
                    const next =
                      event.key === "ArrowRight"
                        ? (index + 1) % tabs.length
                        : event.key === "ArrowLeft"
                          ? (index + tabs.length - 1) % tabs.length
                          : event.key === "Home"
                            ? 0
                            : event.key === "End"
                              ? tabs.length - 1
                              : null;
                    if (next === null) return;
                    event.preventDefault();
                    setTab(next);
                    document.getElementById(`${id}-tab-${next}`)?.focus();
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            <StyleSlider
              label="字号"
              value={draft.font_size}
              unit=" px"
              min={14}
              max={24}
              disabled={busy}
              onChange={(value) => update("font_size", value)}
            />
            <section
              role="tabpanel"
              id={`${id}-panel-0`}
              aria-labelledby={`${id}-tab-0`}
              hidden={tab !== 0}
              tabIndex={0}
            >
              <div className="style-label">
                阅读配色<span>只改变颜色</span>
              </div>
              <div
                className="style-palettes"
                role="group"
                aria-label="阅读配色"
              >
                {readingPalettes.map((palette) => (
                  <button
                    type="button"
                    key={palette.label}
                    disabled={busy}
                    aria-pressed={
                      draft.background_color.toLowerCase() ===
                        palette.background_color &&
                      draft.text_color.toLowerCase() === palette.text_color
                    }
                    onClick={() =>
                      replacePatch({
                        ...patch,
                        background_color: palette.background_color,
                        text_color: palette.text_color,
                      })
                    }
                  >
                    <span
                      className="style-swatch"
                      style={{
                        background: palette.background_color,
                        color: palette.text_color,
                      }}
                      aria-hidden="true"
                    >
                      Aa<span className="style-swatch-check">✓</span>
                    </span>
                    {palette.label}
                  </button>
                ))}
              </div>
              <div className="style-color-fields">
                {(["background_color", "text_color"] as const).map((key) => (
                  <label key={key}>
                    <input
                      type="color"
                      aria-label={
                        key === "background_color" ? "背景颜色" : "文字颜色"
                      }
                      value={draft[key]}
                      disabled={busy}
                      onChange={(event) => update(key, event.target.value)}
                    />
                    <span>
                      {key === "background_color" ? "背景颜色" : "文字颜色"}
                      <small>{draft[key].toUpperCase()}</small>
                    </span>
                  </label>
                ))}
              </div>
              <div className="style-field">
                <div className="style-label">
                  整套预设<span>同时重置字体与排版</span>
                </div>
                <div
                  className="style-presets"
                  role="group"
                  aria-label="预设主题"
                >
                  {Object.entries(themeLabels).map(([key, label]) => {
                    const preset = readingThemes[key as ReadingStyle["theme"]];
                    const selected = Object.entries(preset).every(
                      ([field, value]) =>
                        draft[field as keyof ReadingStyle] === value,
                    );
                    return (
                      <button
                        type="button"
                        key={key}
                        disabled={busy}
                        aria-pressed={selected}
                        onClick={() =>
                          replacePatch({ theme: key as ReadingStyle["theme"] })
                        }
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </section>
            <section
              role="tabpanel"
              id={`${id}-panel-1`}
              aria-labelledby={`${id}-tab-1`}
              hidden={tab !== 1}
              tabIndex={0}
            >
              <div className="style-label">字体</div>
              <div className="style-fonts" role="group" aria-label="字体">
                {fontOptions.map(({ value, label }) => (
                  <button
                    type="button"
                    key={value}
                    disabled={busy}
                    aria-pressed={draft.font_family === value}
                    onClick={() => update("font_family", value)}
                    style={{ fontFamily: readingFonts[value] }}
                  >
                    <span aria-hidden="true">字 Aa</span>
                    <span>{label}</span>
                    <span className="style-font-check" aria-hidden="true">
                      {draft.font_family === value ? "✓" : ""}
                    </span>
                  </button>
                ))}
              </div>
              <StyleChoices
                label="字重"
                value={draft.font_weight}
                options={[
                  { value: 400, label: "标准" },
                  { value: 500, label: "适中" },
                  { value: 600, label: "半粗" },
                  { value: 700, label: "加粗" },
                ]}
                disabled={busy}
                onChange={(value) => update("font_weight", value)}
              />
              <p className="style-help">
                使用设备上的可用字体，中英文字体效果可能因设备而异。
              </p>
            </section>
            <section
              role="tabpanel"
              id={`${id}-panel-2`}
              aria-labelledby={`${id}-tab-2`}
              hidden={tab !== 2}
              tabIndex={0}
            >
              <StyleSlider
                label="内容宽度"
                value={draft.content_width}
                unit=" px"
                min={600}
                max={900}
                step={10}
                disabled={busy}
                onChange={(value) => update("content_width", value)}
              />
              <StyleSlider
                label="行距"
                value={draft.line_height}
                min={1.2}
                max={2}
                step={0.1}
                disabled={busy}
                onChange={(value) => update("line_height", value)}
              />
              <StyleSlider
                label="段距"
                value={draft.paragraph_spacing}
                unit=" px"
                min={0}
                max={40}
                disabled={busy}
                onChange={(value) => update("paragraph_spacing", value)}
              />
              <StyleChoices
                label="对齐方式"
                value={draft.text_align}
                options={[
                  { value: "left", label: "自然左对齐" },
                  { value: "justify", label: "两端对齐" },
                ]}
                disabled={busy}
                onChange={(value) => update("text_align", value)}
              />
              <p className="style-help">
                内容宽度同时作用于标题、摘要与正文；小屏幕自动适应可用空间。
              </p>
            </section>
          </div>
        </div>
        <div className="style-save-area">
          <StyleChoices
            label="应用范围"
            value={scope}
            options={[
              { value: "note", label: "仅本文" },
              { value: "global", label: "所有笔记" },
            ]}
            disabled={busy}
            onChange={setScope}
          />
          <p className="style-help">
            {scope === "global"
              ? "保存为全局默认；已有独立样式的笔记会保留自己的设置。"
              : "为这篇笔记单独设置；选择“本文跟随全局”可恢复全局样式。"}
          </p>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          <div className="style-footer">
            <button
              type="button"
              className="inline-button"
              disabled={
                busy ||
                (scope === "note"
                  ? !Object.keys(overrides).length
                  : !Object.keys(patch).length)
              }
              onClick={() =>
                scope === "note"
                  ? void onReset().catch(() => undefined)
                  : replacePatch({})
              }
            >
              {scope === "note" ? "本文跟随全局" : "撤销本次调整"}
            </button>
            <button
              className="button"
              disabled={busy || !Object.keys(patch).length}
            >
              {busy ? "保存中…" : "保存样式"}
              <span aria-hidden="true">✓</span>
            </button>
          </div>
        </div>
      </form>
    </CollectionDialog>
  );
}
