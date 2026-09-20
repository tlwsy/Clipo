const pendingKey = "clipo:shared-capture";

export function captureKey(): string {
  // getRandomValues also works for ordinary HTTP deployments on a home network.
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

export function extractSharedUrl(params: URLSearchParams): string | null {
  for (const field of ["url", "text", "title"]) {
    const value = params.get(field)?.trim() ?? "";
    const match = value.match(/https?:\/\/[^\s<>"'，。；！？]+/i);
    if (!match) continue;
    try {
      const url = new URL(match[0]);
      if (url.username || url.password) continue;
      url.hash = "";
      return url.href;
    } catch {
      /* Try another share field. */
    }
  }
  return null;
}

export function pendingShare(): { url: string; key: string } | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(pendingKey) ?? "null");
    return value &&
      typeof value.url === "string" &&
      typeof value.key === "string"
      ? value
      : null;
  } catch {
    return null;
  }
}

export function rememberShare(url: string) {
  const previous = pendingShare();
  const value = previous?.url === url ? previous : { url, key: captureKey() };
  sessionStorage.setItem(pendingKey, JSON.stringify(value));
  return value;
}

export function clearShare() {
  sessionStorage.removeItem(pendingKey);
}
export function afterLogin() {
  return pendingShare() ? "/share/" : "/";
}
