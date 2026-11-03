// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useId, useRef, useState, type CSSProperties } from "react";
import Markdown from "react-markdown";
import {
  readingPalettes,
  readingThemes,
  resolvedReadingStyle,
  themeLabels,
  type ReadingStyle,
  type StylePatch,
} from "@/lib/reading";
import { readingColors, seedFromImage } from "@/lib/reading-colors";
import { useReadingAppearance } from "@/lib/use-reading-appearance";
import { ReadingFontPicker } from "./reading-font-picker";
import { CollectionDialog } from "./collection-dialog";

const tabs = ["主题", "字体", "排版"] as const;
function StyleChoices<T extends string | number>({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly { value: T; label: string; disabled?: boolean }[];
  disabled: boolean;
  onChange: (value: T) => void;
}) {
  return (
    <div className="style-field">
      <span className="style-label">{label}</span>
      <div
        className="style-segments"
        role="group"
        aria-label={label}
        style={
          {
            "--choice-count": options.length,
            "--choice-index": Math.max(
              0,
              options.findIndex((item) => item.value === value),
            ),
          } as CSSProperties
        }
      >
        {options.map((option) => (
          <button
            type="button"
            key={option.value}
            aria-pressed={value === option.value}
            disabled={disabled || option.disabled}
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
  const previewContent = useRef<HTMLDivElement>(null);
  const [imageError, setImageError] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [preparingFont, setPreparingFont] = useState(false);
  const [fontPickerRevision, setFontPickerRevision] = useState(0);
  const imageGeneration = useRef(0);
  useEffect(
    () => () => {
      imageGeneration.current++;
    },
    [],
  );
  useEffect(() => {
    imageGeneration.current++;
    setExtracting(false);
    setImageError("");
  }, [scope]);
  const patch = patches[scope];
  const initial = resolvedReadingStyle(
    preferences,
    scope === "global" ? {} : overrides,
  );
  const draft = resolvedReadingStyle(initial, patch);
  const appearance = useReadingAppearance(draft, preview?.text);
  const colors = readingColors(draft, appearance.dark);
  const typography = JSON.stringify([
    draft.font_family,
    draft.online_font,
    draft.font_size,
    draft.font_weight,
    draft.line_height,
    draft.paragraph_spacing,
    draft.content_width,
    draft.text_align,
    appearance.fontStatus,
  ]);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const animation = previewContent.current?.animate(
      [
        { opacity: 0.65, transform: "translateY(3px)" },
        { opacity: 1, transform: "translateY(0)" },
      ],
      { duration: 280, easing: "cubic-bezier(.2,.7,.2,1)" },
    );
    return () => animation?.cancel();
  }, [typography]);
  const paragraphs = (
    preview?.text ||
    "让值得记住的内容，成为自己的知识。\n\n放慢一点，在字里行间发现新的想法。选择适合自己的字体、留白与颜色，让每一次阅读都更自在。"
  )
    .split(/\n+/)
    .filter(Boolean);
  function replacePatch(next: StylePatch) {
    imageGeneration.current++;
    setExtracting(false);
    if (
      !Object.keys(next).length ||
      (Object.keys(next).length === 1 && next.theme)
    ) {
      setFontPickerRevision((value) => value + 1);
    }
    setPatches((current) => ({ ...current, [scope]: next }));
  }
  function update<K extends keyof StylePatch>(key: K, value: StylePatch[K]) {
    setPatches((current) => ({
      ...current,
      [scope]: { ...current[scope], [key]: value },
    }));
  }
  async function extractImage(file?: File) {
    if (!file) return;
    const current = ++imageGeneration.current;
    setExtracting(true);
    setImageError("");
    try {
      const seed = await seedFromImage(file);
      if (current === imageGeneration.current)
        setPatches((drafts) => ({
          ...drafts,
          [scope]: { ...drafts[scope], color_mode: "monet", monet_seed: seed },
        }));
    } catch (cause) {
      if (current === imageGeneration.current)
        setImageError(
          cause instanceof Error
            ? cause.message
            : "图片无法读取，请换一张图片。",
        );
    } finally {
      if (current === imageGeneration.current) setExtracting(false);
    }
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
          if (busy || extracting || preparingFont) return;
          void onSave(patch, scope === "global").catch(() => undefined);
        }}
      >
        <div className="style-workspace">
          <div className="style-preview-stage">
            <div className="style-preview-label">
              <span>效果预览</span>
              <span>标题 · 摘要 · 完整正文</span>
            </div>
            <div
              className="style-preview-paper reader-styled"
              style={appearance.variables}
              tabIndex={0}
              role="region"
              aria-label="阅读效果预览"
            >
              <div
                className="style-preview-content"
                ref={previewContent}
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
                        {preview.summary}
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
            <div
              className="style-tabs"
              role="tablist"
              aria-label="样式分类"
              style={
                {
                  "--choice-count": tabs.length,
                  "--choice-index": tab,
                } as CSSProperties
              }
            >
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
              <StyleChoices
                label="配色方式"
                value={draft.color_mode ?? "custom"}
                options={[
                  { value: "custom", label: "自选配色" },
                  { value: "monet", label: "莫奈取色" },
                  { value: "system", label: "跟随系统" },
                ]}
                disabled={busy || extracting}
                onChange={(value) => update("color_mode", value)}
              />
              {draft.color_mode === "system" && (
                <p className="style-mode-note">
                  随设备自动切换浅色与深色，当前为
                  {appearance.dark ? "深色" : "浅色"}。
                </p>
              )}
              {draft.color_mode === "monet" && (
                <div className="style-monet">
                  <div
                    className="style-monet-sample"
                    style={{
                      background: colors.background,
                      color: colors.text,
                    }}
                  >
                    <span>从一抹颜色，开始阅读</span>
                    <small>MONET · 自然的色调</small>
                  </div>
                  <div className="style-seed-row">
                    <label>
                      种子色
                      <input
                        type="color"
                        aria-label="莫奈种子色"
                        value={draft.monet_seed ?? "#8ca68c"}
                        disabled={busy || extracting}
                        onChange={(event) =>
                          update("monet_seed", event.target.value)
                        }
                      />
                    </label>
                    <label className="style-image-picker">
                      {extracting ? "正在取色…" : "从图片取色"}
                      <input
                        type="file"
                        accept="image/jpeg,image/png,image/webp,image/avif"
                        aria-label="从图片取色"
                        disabled={busy || extracting}
                        onChange={(event) => {
                          void extractImage(event.target.files?.[0]);
                          event.target.value = "";
                        }}
                      />
                    </label>
                  </div>
                  <StyleChoices
                    label="莫奈明暗"
                    value={draft.monet_scheme ?? "system"}
                    options={[
                      { value: "light", label: "浅色" },
                      { value: "dark", label: "深色" },
                      { value: "system", label: "随系统" },
                    ]}
                    disabled={busy}
                    onChange={(value) => update("monet_scheme", value)}
                  />
                  <p className="style-help">
                    图片只在当前设备取色，不会上传。保存颜色后可在其他设备使用。
                  </p>
                  {imageError && (
                    <p className="style-help" role="alert">
                      {imageError}
                    </p>
                  )}
                </div>
              )}
              <div
                hidden={
                  draft.color_mode === "monet" || draft.color_mode === "system"
                }
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
                          color_mode: "custom",
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
              <ReadingFontPicker
                key={`${scope}-${fontPickerRevision}`}
                style={draft}
                busy={busy}
                onPendingChange={setPreparingFont}
                onChange={(values) =>
                  setPatches((drafts) => ({
                    ...drafts,
                    [scope]: { ...drafts[scope], ...values },
                  }))
                }
              >
                <StyleChoices
                  label="字重"
                  value={draft.font_weight}
                  options={[
                    ...([400, 500, 600, 700] as const).map((value, index) => ({
                      value,
                      label: ["标准", "适中", "半粗", "加粗"][index],
                      disabled: !(
                        draft.font_family === "online" && draft.online_font
                          ? draft.online_font.weights
                          : [400, 700]
                      ).includes(value),
                    })),
                  ]}
                  disabled={busy}
                  onChange={(value) => update("font_weight", value)}
                />
                <p className="style-help">
                  {draft.font_family === "online"
                    ? "只提供当前字体真实支持的字重。思源黑体、思源宋体支持四档粗细。"
                    : "本机字体仅提供标准与加粗。选择在线思源黑体或宋体，可使用四档真实字重。"}
                </p>
                {draft.font_family === "online" && (
                  <p
                    className="style-font-status"
                    role="status"
                    data-font-status={appearance.fontStatus}
                  >
                    {appearance.fontMessage}
                    {appearance.fontStatus === "error" && (
                      <button
                        type="button"
                        className="inline-button"
                        disabled={busy}
                        onClick={appearance.retryFont}
                      >
                        重试字体下载
                      </button>
                    )}
                  </p>
                )}
              </ReadingFontPicker>
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
              disabled={
                busy ||
                extracting ||
                preparingFont ||
                !Object.keys(patch).length
              }
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
