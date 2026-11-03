// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  argbFromHex,
  argbFromRgb,
  hexFromArgb,
  Hct,
  QuantizerCelebi,
  Score,
  TonalPalette,
} from "@material/material-color-utilities";
import type { ReadingStyle } from "./reading";

export function readingColors(style: ReadingStyle, systemDark = false) {
  if (style.color_mode === "system")
    return systemDark
      ? {
          background: "#202421",
          text: "#e6e9e2",
          accent: "#a2d6bd",
          dark: true,
        }
      : {
          background: "#fafbf7",
          text: "#242925",
          accent: "#226552",
          dark: false,
        };
  if (style.color_mode === "monet") {
    const source = Hct.fromInt(argbFromHex(style.monet_seed ?? "#8ca68c"));
    const neutral = TonalPalette.fromHueAndChroma(source.hue, 12);
    const primary = TonalPalette.fromHueAndChroma(
      source.hue,
      Math.min(48, Math.max(24, source.chroma)),
    );
    const dark =
      style.monet_scheme === "dark" ||
      (style.monet_scheme !== "light" && systemDark);
    return {
      background: hexFromArgb(neutral.tone(dark ? 12 : 96)),
      text: hexFromArgb(neutral.tone(dark ? 90 : 15)),
      accent: hexFromArgb(primary.tone(dark ? 80 : 35)),
      dark,
    };
  }
  const [red, green, blue] = [1, 3, 5].map((offset) =>
    parseInt(style.background_color.slice(offset, offset + 2), 16),
  );
  const dark = red * 0.299 + green * 0.587 + blue * 0.114 < 140;
  return {
    background: style.background_color,
    text: style.text_color,
    accent: dark ? "#a2d6bd" : "#226552",
    dark,
  };
}
export async function seedFromImage(file: File): Promise<string> {
  if (
    !["image/png", "image/jpeg", "image/webp", "image/avif"].includes(
      file.type,
    ) ||
    file.size > 12 * 1024 * 1024
  )
    throw new Error("请选择 12 MB 以内的 JPG、PNG、WebP 或 AVIF 图片。");
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode().catch(() => {
      throw new Error("图片无法读取，请换一张图片。");
    });
    const canvas = document.createElement("canvas");
    const scale = Math.min(
      1,
      96 / Math.max(image.naturalWidth, image.naturalHeight),
    );
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("当前浏览器无法从图片取色，请使用种子色。");
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const colors: number[] = [];
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i + 3] >= 200)
        colors.push(argbFromRgb(pixels[i], pixels[i + 1], pixels[i + 2]));
    }
    if (!colors.length) throw new Error("图片没有可用的颜色，请换一张图片。");
    return hexFromArgb(Score.score(QuantizerCelebi.quantize(colors, 64))[0]);
  } finally {
    URL.revokeObjectURL(url);
  }
}
