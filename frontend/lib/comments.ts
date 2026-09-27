// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Schema } from "./api";
type Comment = Schema["CommentResponse"];

export function commentThreads(
  visible: Comment[],
  all: Comment[],
): Comment[][] {
  const bySource = new Map(
    all.filter((row) => row.source_id).map((row) => [row.source_id, row]),
  );
  const groups = new Map<number, Comment[]>();
  for (const comment of visible) {
    let root = comment;
    const seen = new Set<number>([comment.id]);
    while (root.parent_source_id) {
      const parent = bySource.get(root.parent_source_id);
      if (!parent || seen.has(parent.id)) break;
      seen.add(parent.id);
      root = parent;
    }
    const group = groups.get(root.id) ?? [];
    group.push(comment);
    groups.set(root.id, group);
  }
  return [...groups.values()]
    .map((group) => group.sort((a, b) => a.position - b.position))
    .sort(
      (a, b) =>
        Math.min(...a.map((row) => row.position)) -
        Math.min(...b.map((row) => row.position)),
    );
}
