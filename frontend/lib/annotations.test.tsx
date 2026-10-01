// SPDX-License-Identifier: AGPL-3.0-or-later
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { AnnotatedText } from "../components/annotated-text";
import { ArticleContent } from "../components/article-content";
import { AnnotationSidebar } from "../components/annotation-sidebar";
import { ReadingStyleSettings } from "../components/reading-style-settings";
import { acceptSession, type Schema } from "./api";
import {
  annotationSegments,
  blockIndices,
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
  type Annotation,
} from "./annotations";
import {
  readingThemes,
  resolvedReadingStyle,
  readingVariables,
  saveDisplay,
  resetDisplay,
} from "./reading";
import type { ArticleBlock } from "./article";

const annotation: Annotation = {
  id: 7,
  block_index: 0,
  start_offset: 1,
  end_offset: 4,
  selected_text: "😀链",
  highlight_color: "yellow",
  note_text: "<script>批注</script>",
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
};
const block = (value: Partial<ArticleBlock>): ArticleBlock => ({
  type: "text",
  text: "",
  alt: "",
  level: 2,
  ordered: false,
  header: false,
  ...value,
});
afterEach(() => vi.unstubAllGlobals());

it("splits overlapping annotations without duplicating UTF-16 text or moving stale anchors", () => {
  const overlap = {
    ...annotation,
    id: 9,
    start_offset: 3,
    end_offset: 5,
    selected_text: "链接",
    highlight_color: "blue" as const,
  };
  const segments = annotationSegments("中😀链接尾", [
    annotation,
    overlap,
    { ...annotation, id: 10, selected_text: "旧内容" },
  ]);
  expect(
    segments.map((part) => "中😀链接尾".slice(part.start, part.end)).join(""),
  ).toBe("中😀链接尾");
  expect(
    segments
      .find((part) => part.start === 3)
      ?.annotations.map((item) => item.id),
  ).toEqual([7, 9]);
  expect(segments.find((part) => part.start === 3)?.color).toBe("blue");
  expect(
    segments.flatMap((part) => part.annotations).some((item) => item.id === 10),
  ).toBe(false);
});

it("preserves inline formatting, links and escaped notes across highlight boundaries", () => {
  const spans: Schema["ContentInline"][] = [
    { text: "中😀", bold: true, italic: false, strike: false, code: false },
    {
      text: "链接尾",
      url: "https://example.com/",
      bold: false,
      italic: true,
      strike: false,
      code: false,
    },
  ];
  const html = renderToStaticMarkup(
    createElement(AnnotatedText, {
      text: "unused",
      spans,
      blockIndex: 0,
      annotations: [annotation],
    }),
  );
  expect(html).toContain("<strong>中<mark");
  expect(html).toContain('href="https://example.com/"');
  expect(html).toContain('data-annotation-block="0"');
  expect(html.match(/data-annotation-ids="7"/g)).toHaveLength(2);
  expect(html).toContain("&lt;script&gt;批注&lt;/script&gt;");
  expect(html).not.toContain("<script>");
});

it("uses preorder indices for nested blocks and excludes annotations on public reading", () => {
  const blocks = [
    block({
      type: "list",
      children: [block({ type: "list_item", text: "中😀链接尾" })],
    }),
    block({
      type: "details",
      text: "展开",
      children: [block({ type: "code", text: "代码" })],
    }),
  ];
  expect([...blockIndices(blocks).values()]).toEqual([0, 1, 2, 3]);
  const props = {
    text: "fallback",
    blocks,
    annotations: [{ ...annotation, block_index: 1 }],
    annotatable: true,
  };
  const html = renderToStaticMarkup(createElement(ArticleContent, props));
  expect(html).toContain('data-annotation-block="1"');
  expect(html).toContain('data-annotation-block="3"');
  expect(html).toContain('data-annotation-ids="7"');
  const publicHtml = renderToStaticMarkup(
    createElement(ArticleContent, { ...props, publicView: true }),
  );
  expect(publicHtml).not.toContain("data-annotation");
  expect(publicHtml).not.toContain("批注");
  const old = renderToStaticMarkup(
    createElement(ArticleContent, {
      text: "中😀链接尾",
      annotations: [annotation],
      annotatable: true,
    }),
  );
  expect(old).toContain('data-annotation-block="0"');
  expect(old).toContain('data-annotation-ids="7"');
});

it("renders sidebar actions and the four reading themes as native accessible controls", () => {
  const html = renderToStaticMarkup(
    createElement(AnnotationSidebar, {
      annotations: [annotation],
      busy: false,
      error: "",
      onJump: () => undefined,
      onUpdate: async () => undefined,
      onDelete: async () => undefined,
      onClose: () => undefined,
    }),
  );
  expect(html).toContain('aria-label="我的标注"');
  expect(html).toContain("编辑标注");
  expect(html).toContain("删除标注");
  expect(html).toContain("&lt;script&gt;");
  const styles = renderToStaticMarkup(
    createElement(ReadingStyleSettings, {
      preferences: readingThemes.comfortable,
      overrides: {},
      busy: false,
      error: "",
      onSave: async () => undefined,
      onReset: async () => undefined,
      onClose: () => undefined,
    }),
  );
  for (const label of [
    "舒适",
    "紧凑",
    "专注",
    "打印",
    "高级调整",
    "本文跟随全局",
  ])
    expect(styles).toContain(label);
  expect(styles).toContain('<option value="global">所有笔记</option>');
});

it("inherits global styles unless a note explicitly chooses its own theme", () => {
  const global = { ...readingThemes.focus, font_size: 24 };
  expect(
    resolvedReadingStyle(global, { font_size: 22, text_align: null }),
  ).toEqual({ ...global, font_size: 22 });
  expect(resolvedReadingStyle(global, { theme: "compact" })).toEqual(
    readingThemes.compact,
  );
  expect(resolvedReadingStyle()).toEqual(readingThemes.comfortable);
  expect(
    readingVariables(resolvedReadingStyle(global))[
      "--reading-size" as keyof ReturnType<typeof readingVariables>
    ],
  ).toBe("24px");
});

it("uses shared authentication and owner checks for annotation and style writes", async () => {
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
    .mockResolvedValueOnce(new Response(JSON.stringify(annotation)))
    .mockResolvedValueOnce(new Response(JSON.stringify(annotation)))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ font_size: 22 })))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  await createAnnotation(
    12,
    {
      block_index: 0,
      start_offset: 1,
      end_offset: 4,
      selected_text: "😀链",
      highlight_color: "yellow",
    },
    1,
  );
  await updateAnnotation(7, { note_text: "修改" }, 1);
  await deleteAnnotation(7, 1);
  await saveDisplay(12, { font_size: 22 }, 1);
  await resetDisplay(12, 1);
  expect(
    fetch.mock.calls.map(([path, options]) => [path, options.method]),
  ).toEqual([
    ["/api/v1/notes/12/annotations", "POST"],
    ["/api/v1/annotations/7", "PATCH"],
    ["/api/v1/annotations/7", "DELETE"],
    ["/api/v1/notes/12/display", "PATCH"],
    ["/api/v1/notes/12/display", "DELETE"],
  ]);
  expect(fetch.mock.calls[0][1].headers.get("Authorization")).toBe(
    "Bearer test-token",
  );
  await expect(deleteAnnotation(7, 2)).rejects.toThrow("登录账号已改变");
  expect(fetch).toHaveBeenCalledTimes(5);
});
