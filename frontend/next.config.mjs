// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
const production = process.env.NODE_ENV === "production";

/** @type {import('next').NextConfig} */
const config = {
  output: production ? "export" : undefined,
  trailingSlash: true,
  skipTrailingSlashRedirect: true,
  poweredByHeader: false,
  reactStrictMode: true,
  // Keep static generation small enough for a 1–2 GB self-hosted build machine.
  experimental: { cpus: 2 },
  ...(production
    ? {}
    : {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: "http://127.0.0.1:8000/api/:path*",
            },
            { source: "/docs", destination: "http://127.0.0.1:8000/docs" },
            {
              source: "/openapi.json",
              destination: "http://127.0.0.1:8000/openapi.json",
            },
          ];
        },
      }),
};

export default config;
