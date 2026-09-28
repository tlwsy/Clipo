// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import { sourceName } from "./source-name";

describe("笔记来源名称", () => {
  it.each([
    ["xiaoheihe", "https://api.xiaoheihe.cn/share", null, "小黑盒"],
    ["xiaohongshu", "https://xhslink.cn/share", null, "小红书"],
    ["bilibili", "https://b23.tv/share", null, "哔哩哔哩"],
    ["youtube", "https://youtu.be/video", null, "YouTube"],
    ["web", "https://example.com/article", "知识 & 阅读", "知识 & 阅读"],
    ["web", "https://example.com/article", "  ", "example.com"],
    ["web", "https://api.xiaoheihe.cn/share", undefined, "小黑盒"],
    [
      "web",
      "https://xiaoheihe.cn.example.com/article",
      null,
      "xiaoheihe.cn.example.com",
    ],
    ["web", "not a URL", null, "网页"],
    ["constructor", "https://example.com", null, "example.com"],
  ])("%s %s → %s", (platform, url, site_name, expected) => {
    expect(sourceName({ platform: platform!, url: url!, site_name })).toBe(
      expected,
    );
  });
});
