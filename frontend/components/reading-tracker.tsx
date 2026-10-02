// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect } from "react";
import { useAccount } from "./app-shell";
import { reportReading, trackReading } from "@/lib/memory";

export function ReadingTracker({ noteId }: { noteId: number }) {
  const user = useAccount();
  useEffect(
    () =>
      trackReading((seconds) => {
        // Best effort; an uncertain response must not replay an additive increment.
        void reportReading(noteId, user.id, seconds).catch(() => undefined);
      }),
    [noteId, user.id],
  );
  return null;
}
