// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import {
  createContext,
  useContext,
  useRef,
  type ReactNode,
  type MutableRefObject,
} from "react";
import type { Schema } from "@/lib/api";

export type NoteListSnapshot = {
  items: Schema["NoteItem"][];
  cursor: string | null;
  query: string;
  draft: string;
  tags: Schema["TagResponse"][];
  tag: string;
  favorite: boolean;
  pages: number;
  scrollY: number;
};

const NoteListContext =
  createContext<MutableRefObject<NoteListSnapshot | null> | null>(null);

// The authenticated layout owns this memory; leaving it (including logout) discards it.
export function NoteListProvider({ children }: { children: ReactNode }) {
  const snapshot = useRef<NoteListSnapshot | null>(null);
  return (
    <NoteListContext.Provider value={snapshot}>
      {children}
    </NoteListContext.Provider>
  );
}

export function useNoteListSnapshot() {
  const snapshot = useContext(NoteListContext);
  if (!snapshot) throw new Error("Note list context is unavailable");
  return snapshot;
}
