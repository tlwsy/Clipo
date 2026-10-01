// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, type Schema } from "./api";
import type { ArticleBlock } from "./article";

export type Annotation = Schema["AnnotationResponse"];
export type TextSelection = Pick<
  Schema["AnnotationCreate"],
  "block_index" | "start_offset" | "end_offset" | "selected_text"
>;
export const highlightColors = {
  yellow: "黄色",
  green: "绿色",
  blue: "蓝色",
  pink: "粉色",
} as const;

export function blockIndices(
  blocks: ArticleBlock[],
): Map<ArticleBlock, number> {
  const result = new Map<ArticleBlock, number>();
  const visit = (items: ArticleBlock[]) => {
    for (const block of items) {
      result.set(block, result.size);
      visit(block.children ?? []);
    }
  };
  visit(blocks);
  return result;
}

export function annotationSegments(text: string, annotations: Annotation[]) {
  const valid = annotations.filter(
    (item) =>
      item.start_offset >= 0 &&
      item.end_offset > item.start_offset &&
      item.end_offset <= text.length &&
      text.slice(item.start_offset, item.end_offset) === item.selected_text,
  );
  const cuts = [
    ...new Set([
      0,
      text.length,
      ...valid.flatMap((item) => [item.start_offset, item.end_offset]),
    ]),
  ].sort((a, b) => a - b);
  return cuts.slice(0, -1).map((start, index) => {
    const end = cuts[index + 1];
    const active = valid
      .filter((item) => item.start_offset <= start && item.end_offset >= end)
      .sort((a, b) => a.id - b.id);
    return {
      start,
      end,
      annotations: active,
      color: [...active].reverse().find((item) => item.highlight_color)
        ?.highlight_color,
    };
  });
}

export function readTextSelection(
  root: HTMLElement,
  selection: Selection | null,
): TextSelection | string | null {
  if (!selection?.rangeCount || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  const blockFor = (node: Node) =>
    (node.nodeType === Node.ELEMENT_NODE
      ? (node as Element)
      : node.parentElement
    )?.closest<HTMLElement>("[data-annotation-block]");
  const start = blockFor(range.startContainer);
  const end = blockFor(range.endContainer);
  if (
    !root.contains(range.startContainer) ||
    !root.contains(range.endContainer)
  )
    return null;
  if (!start || start !== end)
    return "请在同一段、列表项或表格单元格内选择文字，跨段内容请分开标注。";
  const before = range.cloneRange();
  before.selectNodeContents(start);
  before.setEnd(range.startContainer, range.startOffset);
  const offset = before.toString().length;
  const quote = range.toString();
  if (!quote.trim()) return null;
  if (quote.length > 10000)
    return "每条标注最多选择 10000 个字符，请缩小选区。";
  return {
    block_index: Number(start.dataset.annotationBlock),
    start_offset: offset,
    end_offset: offset + quote.length,
    selected_text: quote,
  };
}

export function createAnnotation(
  noteId: number,
  payload: Schema["AnnotationCreate"],
  expectedUserId?: number,
): Promise<Annotation> {
  return api(`/notes/${noteId}/annotations`, {
    method: "POST",
    body: JSON.stringify(payload),
    expectedUserId,
  });
}
export function updateAnnotation(
  id: number,
  payload: Schema["AnnotationUpdate"],
  expectedUserId?: number,
): Promise<Annotation> {
  return api(`/annotations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    expectedUserId,
  });
}
export function deleteAnnotation(
  id: number,
  expectedUserId?: number,
): Promise<void> {
  return api(`/annotations/${id}`, { method: "DELETE", expectedUserId });
}
