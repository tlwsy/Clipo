// SPDX-License-Identifier: AGPL-3.0-or-later
import type { CSSProperties } from "react";
import { api, type Schema } from "./api";

export type ReadingStyle = Schema["ReadingPreferences"];
export type StylePatch = Schema["ReadingStylePatch"];
export const readingThemes: Record<ReadingStyle["theme"], ReadingStyle> = {
  comfortable: {
    theme: "comfortable",
    font_family: "system-ui",
    font_size: 18,
    font_weight: 400,
    line_height: 1.6,
    paragraph_spacing: 16,
    content_width: 720,
    text_align: "left",
    background_color: "#fefce8",
    text_color: "#1c1917",
  },
  compact: {
    theme: "compact",
    font_family: "system-ui",
    font_size: 16,
    font_weight: 400,
    line_height: 1.4,
    paragraph_spacing: 12,
    content_width: 680,
    text_align: "left",
    background_color: "#ffffff",
    text_color: "#0a0a0a",
  },
  focus: {
    theme: "focus",
    font_family: "system-ui",
    font_size: 20,
    font_weight: 400,
    line_height: 1.8,
    paragraph_spacing: 20,
    content_width: 600,
    text_align: "left",
    background_color: "#1c1917",
    text_color: "#fafafa",
  },
  print: {
    theme: "print",
    font_family: "system-ui",
    font_size: 16,
    font_weight: 400,
    line_height: 1.5,
    paragraph_spacing: 12,
    content_width: 900,
    text_align: "justify",
    background_color: "#ffffff",
    text_color: "#000000",
  },
};
export const themeLabels = {
  comfortable: "舒适",
  compact: "紧凑",
  focus: "专注",
  print: "打印",
} as const;
export function resolvedReadingStyle(
  global?: ReadingStyle,
  overrides: StylePatch = {},
): ReadingStyle {
  const base = overrides.theme
    ? readingThemes[overrides.theme]
    : (global ?? readingThemes.comfortable);
  return {
    ...base,
    ...Object.fromEntries(
      Object.entries(overrides).filter(
        ([, value]) => value !== null && value !== undefined,
      ),
    ),
  };
}
export function readingVariables(style: ReadingStyle): CSSProperties {
  return {
    "--reading-font": style.font_family,
    "--reading-size": `${style.font_size}px`,
    "--reading-weight": style.font_weight,
    "--reading-line": style.line_height,
    "--reading-spacing": `${style.paragraph_spacing}px`,
    "--reading-width": `${style.content_width}px`,
    "--reading-align": style.text_align,
    "--reading-background": style.background_color,
    "--reading-color": style.text_color,
  } as CSSProperties;
}
export function saveReadingPreferences(
  payload: StylePatch,
  expectedUserId?: number,
): Promise<ReadingStyle> {
  return api("/user/reading-preferences", {
    method: "PATCH",
    body: JSON.stringify(payload),
    expectedUserId,
  });
}
export function saveDisplay(
  noteId: number,
  payload: StylePatch,
  expectedUserId?: number,
): Promise<StylePatch> {
  return api(`/notes/${noteId}/display`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    expectedUserId,
  });
}
export function resetDisplay(
  noteId: number,
  expectedUserId?: number,
): Promise<void> {
  return api(`/notes/${noteId}/display`, { method: "DELETE", expectedUserId });
}
