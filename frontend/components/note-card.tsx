// SPDX-License-Identifier: AGPL-3.0-or-later
import Link from "next/link";
import { type Schema } from "@/lib/api";
import { sourceName } from "@/lib/source-name";

export function NoteCard({
  note,
  selecting = false,
  selected = false,
  disabled = false,
  onSelect,
  onRemove,
}: {
  note: Schema["NoteItem"];
  selecting?: boolean;
  selected?: boolean;
  disabled?: boolean;
  onSelect?: (checked: boolean) => void;
  onRemove?: () => void;
}) {
  return (
    <article className="note-card">
      {selecting && (
        <label className="checkbox-label note-selection">
          <input
            type="checkbox"
            checked={selected}
            disabled={disabled}
            onChange={(event) => onSelect?.(event.target.checked)}
          />
          选择 {note.title || "无标题笔记"}
        </label>
      )}
      <Link href={`/notes/?id=${note.id}`} className="note-card-link">
        <div className="note-card-meta">
          <span title={sourceName(note)}>{sourceName(note)}</span>
          <span>{note.status === "ready" ? "AI 已整理" : "未生成摘要"}</span>
        </div>
        <h2>
          {note.is_favorite ? "★ " : ""}
          {note.title || "无标题笔记"}
        </h2>
        <div className="tag-list">
          {note.tags.map((item) => (
            <span className="subtle-badge" key={item.id}>
              {item.name}
            </span>
          ))}
        </div>
        <p>{note.summary_excerpt}</p>
        <div className="note-card-footer">
          <span>{note.author || "网页收藏"}</span>
          <time>{new Date(note.created_at).toLocaleDateString("zh-CN")}</time>
        </div>
      </Link>
      {onRemove && (
        <button
          className="inline-button danger"
          disabled={disabled}
          onClick={onRemove}
        >
          从空间移除
        </button>
      )}
    </article>
  );
}
