// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useState } from "react";
import { highlightColors, type Annotation } from "@/lib/annotations";
import type { Schema } from "@/lib/api";

function AnnotationEntry({
  item,
  busy,
  onJump,
  onUpdate,
  onDelete,
}: {
  item: Annotation;
  busy: boolean;
  onJump: () => void;
  onUpdate: (payload: Schema["AnnotationUpdate"]) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [text, setText] = useState(item.note_text ?? "");
  const [color, setColor] = useState(item.highlight_color ?? "");
  return (
    <li className="annotation-entry">
      <button
        className={`annotation-quote highlight-${item.highlight_color ?? "none"}`}
        onClick={onJump}
        title={item.selected_text}
      >
        {Array.from(item.selected_text).slice(0, 20).join("")}
        {Array.from(item.selected_text).length > 20 ? "…" : ""}
      </button>
      <time dateTime={item.created_at}>
        {new Date(item.created_at).toLocaleString("zh-CN")}
      </time>
      {editing ? (
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await onUpdate({
                note_text: text,
                highlight_color: color
                  ? (color as NonNullable<Annotation["highlight_color"]>)
                  : null,
              });
              setEditing(false);
            } catch {
              /* Parent keeps the failure visible and editor open. */
            }
          }}
        >
          <label>
            修改批注
            <textarea
              rows={3}
              maxLength={5000}
              value={text}
              disabled={busy}
              onChange={(event) => setText(event.target.value)}
            />
          </label>
          <label>
            修改高亮颜色
            <select
              value={color}
              disabled={busy}
              onChange={(event) => setColor(event.target.value)}
            >
              <option value="">无高亮</option>
              {Object.entries(highlightColors).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <div className="annotation-actions">
            <button
              className="button small"
              disabled={busy || (!color && !text.trim())}
            >
              保存修改
            </button>
            <button
              type="button"
              className="inline-button"
              disabled={busy}
              onClick={() => setEditing(false)}
            >
              取消
            </button>
          </div>
        </form>
      ) : (
        <>
          {item.note_text && (
            <p className="annotation-note">{item.note_text}</p>
          )}
          <div className="annotation-actions">
            <button
              className="inline-button"
              disabled={busy}
              onClick={() => {
                setText(item.note_text ?? "");
                setColor(item.highlight_color ?? "");
                setEditing(true);
              }}
            >
              编辑标注
            </button>
            {confirm ? (
              <>
                <button
                  className="inline-button danger"
                  disabled={busy}
                  onClick={() => void onDelete().catch(() => undefined)}
                >
                  确认删除标注
                </button>
                <button
                  className="inline-button"
                  disabled={busy}
                  onClick={() => setConfirm(false)}
                >
                  取消
                </button>
              </>
            ) : (
              <button
                className="inline-button danger"
                disabled={busy}
                onClick={() => setConfirm(true)}
              >
                删除标注
              </button>
            )}
          </div>
        </>
      )}
    </li>
  );
}

export function AnnotationSidebar({
  annotations,
  busy,
  error,
  onJump,
  onUpdate,
  onDelete,
  onClose,
}: {
  annotations: Annotation[];
  busy: boolean;
  error: string;
  onJump: (item: Annotation) => void;
  onUpdate: (
    item: Annotation,
    payload: Schema["AnnotationUpdate"],
  ) => Promise<void>;
  onDelete: (item: Annotation) => Promise<void>;
  onClose: () => void;
}) {
  return (
    <aside className="annotation-sidebar" aria-label="我的标注">
      <div className="section-heading">
        <h3>我的标注（{annotations.length}）</h3>
        <button className="inline-button" onClick={onClose}>
          收起
        </button>
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {!annotations.length && (
        <p className="muted">选中正文文字，添加高亮或写下想法。</p>
      )}
      <ul>
        {[...annotations]
          .sort(
            (a, b) =>
              a.block_index - b.block_index ||
              a.start_offset - b.start_offset ||
              a.id - b.id,
          )
          .map((item) => (
            <AnnotationEntry
              key={item.id}
              item={item}
              busy={busy}
              onJump={() => onJump(item)}
              onUpdate={(payload) => onUpdate(item, payload)}
              onDelete={() => onDelete(item)}
            />
          ))}
      </ul>
    </aside>
  );
}
