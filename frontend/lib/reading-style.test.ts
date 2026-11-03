// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, expect, it, vi } from "vitest";
import { readingColors } from "./reading-colors";
import {
  fontStylesheet,
  onlineFontFamily,
  parseCatalog,
  resolveOnlineFont,
  searchFonts,
} from "./reading-fonts";
import {
  readingThemes,
  readingVariables,
  resolvedReadingStyle,
} from "./reading";
const online = {
  id: "noto-sans-sc",
  family: "Noto Sans SC",
  variable: true,
  version: "5.3.1",
  weights: [400, 500, 600, 700] as (400 | 500 | 600 | 700)[],
};
afterEach(() => {
  vi.unstubAllGlobals();
});
it("keeps old preferences compatible and resets online/dynamic settings with a preset", () => {
  const { color_mode, monet_seed, monet_scheme, online_font, ...old } =
    readingThemes.comfortable;
  expect(resolvedReadingStyle(old as typeof readingThemes.comfortable)).toEqual(
    readingThemes.comfortable,
  );
  const style = {
    ...readingThemes.comfortable,
    font_family: "online" as const,
    online_font: online,
    color_mode: "monet" as const,
  };
  expect(resolvedReadingStyle(style, { font_size: 22 })).toEqual({
    ...style,
    font_size: 22,
  });
  expect(resolvedReadingStyle(style, { theme: "print" })).toEqual(
    readingThemes.print,
  );
  expect(readingVariables(style)).toHaveProperty(
    "--reading-font",
    expect.stringContaining('"Noto Sans SC Variable"'),
  );
  expect(readingVariables(style)).toHaveProperty("--reading-weight", 400);
  expect([color_mode, monet_seed, monet_scheme, online_font]).toHaveLength(4);
  expect(
    resolvedReadingStyle(
      { ...style, online_font: { ...online, weights: [400] } },
      { font_weight: 700 },
    ).font_weight,
  ).toBe(400);
});
it("follows live system colors without changing custom palettes", () => {
  const custom = readingThemes.comfortable;
  expect(readingColors(custom, true)).toEqual(readingColors(custom, false));
  const style = { ...custom, color_mode: "system" as const };
  expect(readingColors(style, true).dark).toBe(true);
  expect(readingColors(style, false).dark).toBe(false);
  expect(readingVariables(style, true)).toHaveProperty(
    "--reading-scheme",
    "dark",
  );
});
function luminance(color: string) {
  const rgb = [1, 3, 5]
    .map((i) => parseInt(color.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
it("generates distinct Monet tones with readable contrast for both schemes", () => {
  const colors = new Set();
  for (const seed of [
    "#ff0000",
    "#0000ff",
    "#008800",
    "#000000",
    "#ffffff",
    "#8ca68c",
  ]) {
    for (const dark of [false, true]) {
      const style = {
        ...readingThemes.comfortable,
        color_mode: "monet" as const,
        monet_seed: seed,
      };
      const palette = readingColors(style, dark);
      colors.add(palette.background);
      const [low, high] = [
        luminance(palette.text),
        luminance(palette.background),
      ].sort((a, b) => a - b);
      expect((high + 0.05) / (low + 0.05)).toBeGreaterThan(7);
      expect(palette.dark).toBe(dark);
      expect(
        readingColors({ ...style, monet_scheme: "light" }, true).dark,
      ).toBe(false);
      expect(
        readingColors({ ...style, monet_scheme: "dark" }, false).dark,
      ).toBe(true);
    }
  }
  expect(colors.size).toBeGreaterThan(6);
});
it("searches actual catalog names and Chinese aliases, excluding unsafe entries", () => {
  const fonts = parseCatalog([
    { ...online, subsets: ["chinese-simplified", "latin"], styles: ["normal"] },
    {
      ...online,
      id: "inter",
      family: "Inter",
      subsets: ["latin"],
      styles: ["normal"],
    },
    {
      ...online,
      id: "static-font",
      family: "Static Font",
      weights: [400],
      variable: false,
      subsets: ["latin"],
      styles: ["normal"],
    },
    { ...online, id: "../../evil", subsets: [], styles: ["normal"] },
    {
      ...online,
      family: 'bad";src:url(evil)',
      subsets: [],
      styles: ["normal"],
    },
    { ...online, family: undefined, subsets: [], styles: ["normal"] },
    { ...online, id: "italic", subsets: [], styles: ["italic"] },
  ]);
  expect(fonts).toHaveLength(3);
  expect(searchFonts(fonts, "思源黑体", true).map((f) => f.id)).toEqual([
    "noto-sans-sc",
  ]);
  expect(searchFonts(fonts, "noto sans", false).map((f) => f.id)).toEqual([
    "noto-sans-sc",
  ]);
  expect(searchFonts(fonts, "Inter", true)).toEqual([]);
  expect(searchFonts(fonts, "Inter", false)).toHaveLength(1);
  expect(fonts.find((f) => f.id === "static-font")?.weights).toEqual([400]);
});
it("pins CDN stylesheets, uses variable font names and rejects arbitrary URLs or weights", async () => {
  expect(onlineFontFamily(online)).toBe("Noto Sans SC Variable");
  expect(fontStylesheet(online, 500)).toBe(
    "https://cdn.jsdelivr.net/npm/@fontsource-variable/noto-sans-sc@5.3.1/index.css",
  );
  expect(fontStylesheet({ ...online, variable: false }, 600)).toContain(
    "@fontsource/noto-sans-sc@5.3.1/600.css",
  );
  expect(() => fontStylesheet({ ...online, weights: [400] }, 500)).toThrow();
  for (const patch of [
    { id: "https://evil.com" },
    { family: 'font"' },
    { version: "latest?url=bad" },
  ])
    expect(() => fontStylesheet({ ...online, ...patch }, 400)).toThrow();
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ latest: "5.1.0", latestVariable: "5.3.1" }),
      ),
    );
  vi.stubGlobal("fetch", fetch);
  expect(await resolveOnlineFont({ ...online, subsets: ["latin"] })).toEqual(
    online,
  );
  expect(fetch.mock.calls[0][1]).toMatchObject({
    credentials: "omit",
    referrerPolicy: "no-referrer",
  });
});

it("recreates failed font faces on retry and shares loaded stylesheets", async () => {
  const { loadOnlineFont } = await import("./reading-fonts");
  const links: { onload?: () => void; remove: ReturnType<typeof vi.fn> }[] = [];
  const load = vi
    .fn()
    .mockRejectedValueOnce(new Error("network"))
    .mockResolvedValue([{}]);
  vi.stubGlobal("document", {
    createElement: () => {
      const link = { remove: vi.fn() };
      links.push(link);
      return link;
    },
    head: {
      append: (link: { onload: () => void }) =>
        queueMicrotask(() => link.onload()),
    },
    fonts: { load },
  });
  await expect(loadOnlineFont(online, 400, "阅读")).rejects.toThrow("network");
  expect(links[0].remove).toHaveBeenCalledOnce();
  await loadOnlineFont(online, 400, "阅读");
  await loadOnlineFont(online, 500, "阅读");
  expect(links).toHaveLength(2);
  expect(load).toHaveBeenLastCalledWith(
    '500 18px "Noto Sans SC Variable"',
    "Aa 阅读",
  );
});
