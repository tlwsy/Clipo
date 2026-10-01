// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, type Schema } from "./api";

export type Collection = Schema["CollectionResponse"];
export const collectionColors: Record<
  Collection["color"],
  { label: string; value: string }
> = {
  blue: { label: "蓝色", value: "#2563eb" },
  green: { label: "绿色", value: "#15803d" },
  purple: { label: "紫色", value: "#7e22ce" },
  orange: { label: "橙色", value: "#c2410c" },
  pink: { label: "粉色", value: "#be185d" },
  red: { label: "红色", value: "#b91c1c" },
  teal: { label: "青色", value: "#0f766e" },
  yellow: { label: "黄色", value: "#a16207" },
};
export const collectionIcons = {
  folder: "文件夹",
  briefcase: "工作",
  book: "书籍",
  heart: "爱心",
  laptop: "电脑",
  star: "星星",
} as const;

export async function loadCollections(noteId?: number): Promise<Collection[]> {
  return (
    await api<Schema["CollectionPage"]>(
      `/collections${noteId ? `?note_id=${noteId}` : ""}`,
    )
  ).collections;
}
export function saveCollection(
  payload: Schema["CollectionCreate"],
  id?: number,
): Promise<Collection> {
  return api(`/collections${id ? `/${id}` : ""}`, {
    method: id ? "PATCH" : "POST",
    body: JSON.stringify(payload),
  });
}
export function deleteCollection(id: number): Promise<void> {
  return api(`/collections/${id}`, { method: "DELETE" });
}
export function changeCollectionNotes(
  id: number,
  noteIds: number[],
  remove = false,
): Promise<void> {
  return api(`/collections/${id}/notes`, {
    method: remove ? "DELETE" : "POST",
    body: JSON.stringify({
      note_ids: noteIds,
    } satisfies Schema["CollectionNotes"]),
  });
}
