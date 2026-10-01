// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useState } from "react";
import {
  highlightColors,
  type Annotation,
  type TextSelection,
} from "@/lib/annotations";
import type { Schema } from "@/lib/api";

export function AnnotationToolbar({
  selection,
  position,
  busy,
  error,
  onSave,
  onClose,
}: {
  selection: TextSelection;
  position: { left: number; top: number };
  busy: boolean;
  error: string;
  onSave: (payload: Schema["AnnotationCreate"]) => void;
  onClose: () => void;
}) {
  const [writing, setWriting] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [color, setColor] = useState<Annotation["highlight_color"]>(null);
  return (
    <div
      className="annotation-toolbar"
      role="dialog"
      aria-label="添加标注"
      style={position}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !busy) {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <div className="section-heading">
        <strong>标注选中文字</strong>
        <button
          type="button"
          className="inline-button"
          disabled={busy}
          onClick={onClose}
        >
          关闭
        </button>
      </div>
      <p className="annotation-preview">{selection.selected_text}</p>
      <div className="annotation-colors" role="group" aria-label="高亮颜色">
        {Object.entries(highlightColors).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`highlight-${key}`}
            aria-label={`${label}高亮`}
            aria-pressed={color === key}
            disabled={busy}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              const next = key as NonNullable<Annotation["highlight_color"]>;
              setColor(next);
              if (!writing) onSave({ ...selection, highlight_color: next });
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {writing ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            onSave({
              ...selection,
              highlight_color: color,
              note_text: noteText,
            });
          }}
        >
          <label>
            批注内容
            <textarea
              value={noteText}
              maxLength={5000}
              rows={3}
              onChange={(event) => setNoteText(event.target.value)}
              disabled={busy}
            />
          </label>
          <button
            type="submit"
            className="button small"
            disabled={busy || (!color && !noteText.trim())}
          >
            {busy ? "保存中…" : "保存批注"}
          </button>
        </form>
      ) : (
        <button
          type="button"
          className="inline-button"
          disabled={busy}
          onClick={() => setWriting(true)}
        >
          添加批注
        </button>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
