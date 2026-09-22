// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, type Schema } from "./api";

export function createShortcutPairing(name: string, userId: number) {
  return api<Schema["IssuedPairing"]>("/shortcuts/pairings", {
    method: "POST",
    expectedUserId: userId,
    body: JSON.stringify({ name, server_url: window.location.origin }),
  });
}

export function pairingExpired(
  pairing: Schema["PairingStatus"],
  now = Date.now(),
) {
  return (
    pairing.status === "expired" ||
    (pairing.status === "pending" && Date.parse(pairing.expires_at) <= now)
  );
}

export async function copySetupInput(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    // Local HTTP hotspots lack the asynchronous clipboard API.
    const input = document.createElement("textarea");
    input.value = value;
    input.style.position = "fixed";
    input.style.opacity = "0";
    input.setAttribute("readonly", "");
    document.body.appendChild(input);
    input.focus();
    input.select();
    input.setSelectionRange(0, value.length);
    try {
      return document.execCommand("copy");
    } catch {
      return false;
    } finally {
      input.remove();
    }
  }
}
