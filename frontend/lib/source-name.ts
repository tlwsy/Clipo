// SPDX-License-Identifier: AGPL-3.0-or-later
const platforms: Record<string, string> = {
  xiaoheihe: "小黑盒",
  xiaohongshu: "小红书",
  bilibili: "哔哩哔哩",
  youtube: "YouTube",
};
const domains: Record<string, string> = {
  "xiaoheihe.cn": "小黑盒",
  "xiaohongshu.com": "小红书",
  "xhslink.com": "小红书",
  "xhslink.cn": "小红书",
  "bilibili.com": "哔哩哔哩",
  "b23.tv": "哔哩哔哩",
  "youtube.com": "YouTube",
  "youtu.be": "YouTube",
};

export function sourceName(source: {
  platform: string;
  url: string;
  site_name?: string | null;
}): string {
  const platform = Object.hasOwn(platforms, source.platform)
    ? platforms[source.platform]
    : undefined;
  if (platform) return platform;
  if (source.site_name?.trim()) return source.site_name.trim();
  try {
    const hostname = new URL(source.url).hostname;
    // Also support older offline notes whose platform was recorded as "web".
    for (const [domain, name] of Object.entries(domains))
      if (hostname === domain || hostname.endsWith(`.${domain}`)) return name;
    return hostname;
  } catch {
    return "网页";
  }
}
