// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import {
  articleImages,
  articleUrl,
  steamCardUrl,
  type ArticleBlock,
} from "./article";

const block = (value: Partial<ArticleBlock>): ArticleBlock => ({
  type: "text",
  text: "",
  alt: "",
  level: 2,
  ordered: false,
  header: false,
  ...value,
});

describe("captured article rendering", () => {
  it("rejects executable, credentialed and local links from stale offline data", () => {
    for (const url of [
      "javascript:alert(1)",
      "data:text/html,bad",
      "http://127.0.0.1/x",
      "http://localhost./x",
      "https://a:b@example.com",
      "https://example.com:8000",
      "https://example.com\\@127.0.0.1",
    ])
      expect(articleUrl(url)).toBeUndefined();
    expect(articleUrl("https://example.com/image.png")).toBe(
      "https://example.com/image.png",
    );
  });
  it("does not link mismatched cards or Epic identifiers to Steam", () => {
    const card = block({
      type: "game_card",
      appid: "12345",
      store: "steam",
      url: "https://store.steampowered.com/app/12345/",
    });
    expect(steamCardUrl(card)).toBe(card.url);
    expect(steamCardUrl({ ...card, appid: "9" })).toBeUndefined();
    expect(steamCardUrl({ ...card, store: "epic" })).toBeUndefined();
    expect(
      steamCardUrl({ ...card, url: "https://attacker.example/" }),
    ).toBeUndefined();
  });
  it("recognizes nested image positions and card covers without repeating a gallery", () => {
    const nested = [
      block({
        type: "details",
        children: [block({ type: "image", url: "https://example.com/a.png" })],
      }),
      block({ type: "game_card", image: "https://example.com/cover.png" }),
    ];
    expect([...articleImages(nested)]).toEqual([
      "https://example.com/a.png",
      "https://example.com/cover.png",
    ]);
  });
});
