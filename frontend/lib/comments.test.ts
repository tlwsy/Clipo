// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { commentThreads } from "./comments";
import { NoteComments } from "../components/note-comments";
import type { Schema } from "./api";

function comment(
  id: number,
  parent: number | null,
  score: number | null,
): Schema["CommentResponse"] {
  return {
    id,
    position: id - 1,
    source_id: String(id),
    parent_source_id: parent ? String(parent) : null,
    author: `作者${id}`,
    content: `内容${id}`,
    likes: 1,
    replies: 0,
    ai_score: score,
    ai_reason: null,
    is_valuable: score !== null && score >= 0.6,
  };
}
describe("comment discussion", () => {
  it("groups valuable replies through hidden parents without leaking hidden text", () => {
    const all = [
      comment(1, null, 0.1),
      comment(2, 1, 0.9),
      comment(3, 2, 0.8),
      comment(4, null, null),
    ];
    expect(
      commentThreads(
        all.filter((row) => row.is_valuable),
        all,
      ).map((group) => group.map((row) => row.id)),
    ).toEqual([[2, 3]]);
    const html = renderToStaticMarkup(
      createElement(NoteComments, {
        note: {
          comments: all,
          content: { comment_capture_limit: 100 },
          comment_score_error: null,
          comment_insights: [{ text: "整合建议", indices: [1, 2] }],
        } as Schema["NoteResponse"],
      }),
    );
    expect(html).not.toContain("内容1");
    expect(html).toContain("内容2");
    expect(html).toContain("未评分评论");
    expect(html).toContain('href="#comment-1"');
    expect(html).toContain("整合建议");
  });
  it("handles broken references and cycles", () => {
    const rows = [comment(1, 2, 0.8), comment(2, 1, 0.7), comment(3, 99, 0.9)];
    expect(commentThreads(rows, rows).flat()).toHaveLength(3);
  });
});
