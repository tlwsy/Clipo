// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Schema } from "./api";

export type OnlineFont = Schema["OnlineFont"];
export type CatalogFont = {
  id: string;
  family: string;
  weights: OnlineFont["weights"];
  variable: boolean;
  subsets: string[];
};
const apiRoot = "https://api.fontsource.org/v1";
const fontId = /^[a-z0-9][a-z0-9-]{0,79}$/;
const fontFamily = /^[A-Za-z0-9][A-Za-z0-9 ._+\-]{0,99}$/;
const fontVersion = /^\d{1,3}\.\d{1,3}\.\d{1,3}$/;
export const fontAliases: Record<string, string> = {
  "noto-sans-sc": "思源黑体 · 简体中文",
  "noto-serif-sc": "思源宋体 · 简体中文",
  "noto-sans-tc": "思源黑体 · 繁体中文",
  "noto-serif-tc": "思源宋体 · 繁体中文",
  "ma-shan-zheng": "马善政楷书",
  "long-cang": "龙藏体",
  "zhi-mang-xing": "志莽行书",
  "liu-jian-mao-cao": "刘建毛草",
  "zcool-xiao-wei": "站酷小薇",
  "zcool-qingke-huangyou": "站酷庆科黄油体",
  "zcool-kuaile": "站酷快乐体",
  inter: "Inter · 拉丁文字",
};
export function parseCatalog(value: unknown): CatalogFont[] {
  if (!Array.isArray(value))
    throw new Error("字体目录格式不正确，请稍后重试。");
  return value
    .flatMap((item): CatalogFont[] => {
      if (
        !item ||
        typeof item.id !== "string" ||
        typeof item.family !== "string" ||
        !fontId.test(item.id) ||
        !fontFamily.test(item.family) ||
        !Array.isArray(item.weights) ||
        !Array.isArray(item.subsets) ||
        !Array.isArray(item.styles) ||
        !item.styles.includes("normal") ||
        typeof item.variable !== "boolean"
      )
        return [];
      const weights = ([400, 500, 600, 700] as const).filter((w) =>
        item.weights.includes(w),
      );
      return weights.length
        ? [
            {
              id: item.id,
              family: item.family,
              weights,
              variable: item.variable,
              subsets: item.subsets.filter(
                (s: unknown): s is string => typeof s === "string",
              ),
            },
          ]
        : [];
    })
    .sort((a, b) => {
      const priority = (font: CatalogFont) =>
        ["noto-sans-sc", "noto-serif-sc"].indexOf(font.id);
      const left = priority(a),
        right = priority(b);
      return (
        (left < 0 ? 99 : left) - (right < 0 ? 99 : right) ||
        a.family.localeCompare(b.family)
      );
    });
}
async function getMetadata(path: string): Promise<unknown> {
  const response = await fetch(`${apiRoot}/${path}`, {
    credentials: "omit",
    referrerPolicy: "no-referrer",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok)
    throw new Error("字体库暂时无法连接，请重试或使用本机字体。");
  return response.json();
}
let catalog: Promise<CatalogFont[]> | undefined;
export function loadFontCatalog(): Promise<CatalogFont[]> {
  return (catalog ??= getMetadata("fonts")
    .then(parseCatalog)
    .catch((error) => {
      catalog = undefined;
      throw error;
    }));
}
export function searchFonts(
  fonts: CatalogFont[],
  query: string,
  chinese: boolean,
): CatalogFont[] {
  const terms = query.trim().toLowerCase().split(/\s+/);
  return fonts.filter(
    (font) =>
      (!chinese || font.subsets.some((s) => s.startsWith("chinese"))) &&
      terms.every((term) =>
        `${font.family} ${font.id} ${fontAliases[font.id] ?? ""}`
          .toLowerCase()
          .includes(term),
      ),
  );
}
export async function resolveOnlineFont(
  font: CatalogFont,
): Promise<OnlineFont> {
  if (!fontId.test(font.id) || !fontFamily.test(font.family))
    throw new Error("字体信息无效。");
  const metadata = (await getMetadata(`version/${font.id}`)) as {
    latest?: string;
    latestVariable?: string;
  };
  const version = font.variable ? metadata.latestVariable : metadata.latest;
  if (!version || !fontVersion.test(version))
    throw new Error("这个字体暂时无法加载，请选择其他字体。");
  return {
    id: font.id,
    family: font.family,
    variable: font.variable,
    weights: font.weights,
    version,
  };
}
export function onlineFontFamily(font: OnlineFont): string {
  return `${font.family}${font.variable ? " Variable" : ""}`;
}
export function fontStylesheet(font: OnlineFont, weight: number): string {
  if (
    !fontId.test(font.id) ||
    !fontFamily.test(font.family) ||
    !fontVersion.test(font.version) ||
    !font.weights.includes(weight as OnlineFont["weights"][number])
  )
    throw new Error("字体信息无效。");
  // The npm stylesheet preserves unicode-range for every CJK segment.
  return `https://cdn.jsdelivr.net/npm/@fontsource${font.variable ? "-variable" : ""}/${font.id}@${font.version}/${font.variable ? "index" : weight}.css`;
}
const sheets = new Map<string, Promise<void>>();
const links = new Map<string, HTMLLinkElement>();
function loadStylesheet(url: string): Promise<void> {
  let pending = sheets.get(url);
  if (pending) return pending;
  pending = new Promise<void>((resolve, reject) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = url;
    link.crossOrigin = "anonymous";
    link.referrerPolicy = "no-referrer";
    const timer = setTimeout(() => fail(), 20000);
    const fail = () => {
      clearTimeout(timer);
      link.remove();
      reject(new Error("字体下载失败，暂用本机字体。"));
    };
    link.onload = () => {
      clearTimeout(timer);
      resolve();
    };
    link.onerror = fail;
    links.set(url, link);
    document.head.append(link);
  }).catch((error) => {
    sheets.delete(url);
    links.delete(url);
    throw error;
  });
  sheets.set(url, pending);
  return pending;
}
export async function loadOnlineFont(
  font: OnlineFont,
  weight: number,
  sample: string,
): Promise<void> {
  const url = fontStylesheet(font, weight);
  await loadStylesheet(url);
  const link = links.get(url);
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const faces = await Promise.race([
      document.fonts.load(
        `${weight} 18px "${onlineFontFamily(font)}"`,
        `Aa ${sample.slice(0, 80)}`,
      ),
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error("字体下载超时，暂用本机字体。")),
          20000,
        );
      }),
    ]);
    if (!faces.length) throw new Error("字体未能加载，暂用本机字体。");
  } catch (error) {
    // A failed FontFace stays rejected. Recreate its stylesheet on retry.
    if (links.get(url) === link) {
      link?.remove();
      links.delete(url);
      sheets.delete(url);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
