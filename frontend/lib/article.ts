// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Schema } from "./api";

export type ArticleBlock = Schema["CapturedBlock-Output"];

export function articleUrl(value?: string | null): string | undefined {
  if (!value || /[\u0000-\u0020\\]/.test(value)) return undefined;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      (url.port && !["80", "443"].includes(url.port)) ||
      /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[|0\.|169\.254\.)/.test(
        host,
      ) ||
      /\.(local|internal|localhost)$/.test(host)
    )
      return undefined;
    return url.href;
  } catch {
    return undefined;
  }
}

export function articleImages(blocks: ArticleBlock[]): Set<string> {
  const urls = new Set<string>();
  function walk(rows: ArticleBlock[], depth: number) {
    if (depth > 16) return;
    for (const block of rows) {
      if (block.type === "image" && block.url) urls.add(block.url);
      if (block.type === "game_card" && block.image) urls.add(block.image);
      walk(block.children ?? [], depth + 1);
    }
  }
  walk(blocks, 0);
  return urls;
}

export function steamCardUrl(block: ArticleBlock): string | undefined {
  const url = articleUrl(block.url);
  return block.store === "steam" &&
    block.appid &&
    /^\d{1,12}$/.test(block.appid) &&
    url === `https://store.steampowered.com/app/${block.appid}/`
    ? url
    : undefined;
}
