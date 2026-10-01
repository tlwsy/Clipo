// SPDX-License-Identifier: AGPL-3.0-or-later
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { CollectionList } from "../components/collection-list";
import { NoteCard } from "../components/note-card";
import { acceptSession, type Schema } from "./api";
import {
  changeCollectionNotes,
  loadCollections,
  type Collection,
} from "./collections";

const space: Collection = {
  id: 7,
  name: "工作 <script>",
  color: "blue",
  icon: "book",
  note_count: 2,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
};
const note: Schema["NoteItem"] = {
  id: 12,
  title: "测试笔记",
  url: "https://example.com",
  platform: "generic",
  author: null,
  summary_excerpt: "摘要",
  status: "ready",
  created_at: space.created_at,
  is_favorite: false,
  tags: [],
};
afterEach(() => vi.unstubAllGlobals());
it("renders private collection links, counts and accessible actions with escaped names", () => {
  const html = renderToStaticMarkup(
    createElement(CollectionList, {
      collections: [space],
      onEdit: () => undefined,
      onDelete: () => undefined,
    }),
  );
  expect(html).toMatch(/href="\/collections\/?\?id=7"/);
  expect(html).toContain("2 篇笔记");
  expect(html).toContain("工作 &lt;script&gt;");
  expect(html).toContain('aria-label="编辑空间');
  expect(html).not.toContain("<script>");
});
it("keeps selection outside note links and disables additions at the selection limit", () => {
  const html = renderToStaticMarkup(
    createElement(NoteCard, {
      note,
      selecting: true,
      selected: true,
      disabled: true,
      onSelect: () => undefined,
    }),
  );
  expect(html).toMatch(/type="checkbox"[^>]*disabled=""[^>]*checked=""/);
  expect(html.indexOf("</label>")).toBeLessThan(html.indexOf("<a "));
  expect(html).toMatch(/href="\/notes\/?\?id=12"/);
  const normal = renderToStaticMarkup(createElement(NoteCard, { note }));
  expect(normal).not.toContain('type="checkbox"');
});
it("uses the shared authenticated client and preserves DELETE membership bodies", async () => {
  acceptSession({
    access_token: "test-token",
    refresh_token: "unused",
    expires_in: 900,
    user: {
      id: 1,
      username: "test",
      email: "test@example.com",
      is_admin: true,
    },
  });
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ collections: [space] })),
    )
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  expect(await loadCollections(12)).toEqual([space]);
  await changeCollectionNotes(7, [12], true);
  expect(fetch.mock.calls[0][0]).toBe("/api/v1/collections?note_id=12");
  const [url, options] = fetch.mock.calls[1];
  expect(url).toBe("/api/v1/collections/7/notes");
  expect(options.method).toBe("DELETE");
  expect(JSON.parse(options.body)).toEqual({ note_ids: [12] });
  expect(options.headers.get("Authorization")).toBe("Bearer test-token");
});
