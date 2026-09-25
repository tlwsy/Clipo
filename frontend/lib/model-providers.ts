// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

export const modelProviders = [
  {
    id: "dashscope",
    name: "阿里云百炼（中国内地）",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  },
  { id: "deepseek", name: "DeepSeek", baseUrl: "https://api.deepseek.com" },
  {
    id: "siliconflow",
    name: "硅基流动",
    baseUrl: "https://api.siliconflow.cn/v1",
  },
  { id: "openai", name: "OpenAI", baseUrl: "https://api.openai.com/v1" },
];

export function providerForUrl(url: string): string {
  return (
    modelProviders.find(
      (provider) => provider.baseUrl === url.replace(/\/+$/, ""),
    )?.id ?? "custom"
  );
}
