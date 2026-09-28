// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { NoteListProvider } from "@/components/note-list-state";

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <NoteListProvider>{children}</NoteListProvider>
    </AppShell>
  );
}
