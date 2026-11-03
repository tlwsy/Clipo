// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  readingFonts,
  type ReadingStyle,
  type StylePatch,
} from "@/lib/reading";
import {
  fontAliases,
  loadFontCatalog,
  resolveOnlineFont,
  searchFonts,
  type CatalogFont,
} from "@/lib/reading-fonts";

const localFonts = [
  { value: "system-ui", label: "系统字体" },
  { value: "serif", label: "宋体 / 衬线" },
  { value: "sans-serif", label: "无衬线" },
] as const;
export function ReadingFontPicker({
  style,
  busy,
  onChange,
  onPendingChange,
  children,
}: {
  children: ReactNode;
  style: ReadingStyle;
  busy: boolean;
  onPendingChange: (value: boolean) => void;
  onChange: (patch: StylePatch) => void;
}) {
  const [open, setOpen] = useState(style.font_family === "online");
  const [fonts, setFonts] = useState<CatalogFont[]>([]);
  const [query, setQuery] = useState("");
  const [chinese, setChinese] = useState(true);
  const [limit, setLimit] = useState(12);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    onPendingChange(Boolean(pending));
    return () => onPendingChange(false);
  }, [pending, onPendingChange]);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError("");
    void loadFontCatalog()
      .then((items) => {
        if (active) setFonts(items);
      })
      .catch(() => {
        if (active) setError("暂时连不上字体库，请检查网络后重试。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open, retry]);
  async function choose(font: CatalogFont) {
    const current = ++generation.current;
    setPending(font.id);
    setError("");
    try {
      const online = await resolveOnlineFont(font);
      if (current !== generation.current) return;
      onChange({
        font_family: "online",
        online_font: online,
        font_weight: online.weights.includes(style.font_weight)
          ? style.font_weight
          : online.weights[0],
      });
    } catch {
      if (current === generation.current)
        setError("这个字体暂时无法加载，请重试或选择其他字体。");
    } finally {
      if (current === generation.current) setPending("");
    }
  }
  const results = searchFonts(fonts, query, chinese);
  return (
    <div className="style-font-picker">
      <div className="style-label">
        本机字体<span>标准 / 加粗</span>
      </div>
      <div className="style-local-fonts" role="group" aria-label="字体">
        {localFonts.map(({ value, label }) => (
          <button
            type="button"
            key={value}
            disabled={busy}
            aria-pressed={style.font_family === value}
            style={{ fontFamily: readingFonts[value] }}
            onClick={() => {
              generation.current++;
              setPending("");
              onChange({
                font_family: value,
                font_weight: style.font_weight < 600 ? 400 : 700,
              });
            }}
          >
            <span aria-hidden="true">字 Aa</span>
            <span>{label}</span>
          </button>
        ))}
      </div>
      {style.font_family === "online" && style.online_font && (
        <p className="style-active-font">
          已选：{fontAliases[style.online_font.id] ?? style.online_font.family}
        </p>
      )}
      {children}
      <button
        className="style-library-toggle"
        type="button"
        aria-expanded={open}
        disabled={busy}
        onClick={() => setOpen(!open)}
      >
        <span>
          在线字体库 <small>Fontsource</small>
        </span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="style-font-library">
          <label className="style-font-search">
            搜索在线字体
            <input
              type="search"
              value={query}
              placeholder="思源、Noto、Inter…"
              disabled={busy}
              onChange={(event) => {
                setQuery(event.target.value);
                setLimit(12);
              }}
            />
          </label>
          <div className="style-font-filter" role="group" aria-label="字体语言">
            {[true, false].map((value) => (
              <button
                key={String(value)}
                type="button"
                disabled={busy}
                aria-pressed={chinese === value}
                onClick={() => {
                  setChinese(value);
                  setLimit(12);
                }}
              >
                {value ? "支持中文" : "全部语言"}
              </button>
            ))}
          </div>
          {loading && (
            <p className="style-help" role="status">
              正在载入字体目录…
            </p>
          )}
          {error && (
            <p className="style-help" role="alert">
              {error}{" "}
              <button
                type="button"
                className="inline-button"
                disabled={busy}
                onClick={() => {
                  setRetry(retry + 1);
                }}
              >
                重试字体目录
              </button>
            </p>
          )}
          {!loading && fonts.length > 0 && (
            <>
              <p className="style-help" role="status">
                {results.length
                  ? `找到 ${results.length} 款字体，点击即可预览`
                  : "没有找到字体，试试英文名称或全部语言。"}
              </p>
              <div
                className="style-font-results"
                role="group"
                aria-label="在线字体"
              >
                {results.slice(0, limit).map((font) => (
                  <button
                    type="button"
                    key={font.id}
                    disabled={busy}
                    aria-pressed={
                      style.font_family === "online" &&
                      style.online_font?.id === font.id
                    }
                    onClick={() => void choose(font)}
                  >
                    <span>
                      <strong>{fontAliases[font.id] ?? font.family}</strong>
                      <small>
                        {font.family} ·{" "}
                        {font.variable
                          ? "可变字体"
                          : `${font.weights.length} 档字重`}
                      </small>
                    </span>
                    <span aria-hidden="true">
                      {pending === font.id
                        ? "…"
                        : style.font_family === "online" &&
                            style.online_font?.id === font.id
                          ? "✓"
                          : "+"}
                    </span>
                  </button>
                ))}
              </div>
              {results.length > limit && (
                <button
                  className="style-more-fonts"
                  type="button"
                  disabled={busy}
                  onClick={() => setLimit(limit + 12)}
                >
                  显示更多字体
                </button>
              )}
            </>
          )}
          <p className="style-help">
            选择后从在线字体库下载，首次加载需要联网。仅支持拉丁文字的字体会保留中文回退字体。
          </p>
        </div>
      )}
    </div>
  );
}
