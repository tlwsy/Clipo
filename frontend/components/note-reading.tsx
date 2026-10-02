// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useRef, useState } from "react";
import { errorMessage, type Schema } from "@/lib/api";
import {
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
  readTextSelection,
  type Annotation,
  type TextSelection,
} from "@/lib/annotations";
import {
  readingVariables,
  resolvedReadingStyle,
  saveReadingPreferences,
  saveDisplay,
  resetDisplay,
  type StylePatch,
} from "@/lib/reading";
import { readAccount, saveNotes } from "@/lib/offline-store";
import { ArticleContent } from "./article-content";
import { AnnotationToolbar } from "./annotation-toolbar";
import { AnnotationSidebar } from "./annotation-sidebar";
import { ReadingStyleSettings } from "./reading-style-settings";

export function NoteReading({
  note,
  onChange,
}: {
  note: Schema["NoteResponse"];
  onChange: (note: Schema["NoteResponse"]) => void;
}) {
  const surface = useRef<HTMLDivElement>(null);
  const [selection, setSelection] = useState<TextSelection | null>(null);
  const [position, setPosition] = useState({ left: 0, top: 0 });
  const [selectionHint, setSelectionHint] = useState("");
  const [sidebar, setSidebar] = useState(false);
  const [styles, setStyles] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const current = useRef(note);
  current.current = note;
  const annotations = note.annotations ?? [];
  useEffect(() => {
    const detect = () => {
      if (
        !surface.current ||
        document.activeElement?.closest(".annotation-toolbar") ||
        document.querySelector("dialog[open]")
      )
        return;
      const native = window.getSelection();
      const value = readTextSelection(surface.current, native);
      if (typeof value === "string") {
        setSelection(null);
        setSelectionHint(value);
        return;
      }
      setSelectionHint("");
      setSelection(value);
      if (value && native?.rangeCount) {
        const rect = native.getRangeAt(0).getBoundingClientRect();
        setPosition({
          left: Math.max(12, Math.min(rect.left, window.innerWidth - 348)),
          top: Math.max(
            12,
            Math.min(rect.bottom + 8, window.innerHeight - 340),
          ),
        });
      }
    };
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelection(null);
    };
    document.addEventListener("selectionchange", detect);
    document.addEventListener("keyup", close);
    window.addEventListener("resize", detect);
    window.addEventListener("scroll", detect, true);
    return () => {
      document.removeEventListener("selectionchange", detect);
      document.removeEventListener("keyup", close);
      window.removeEventListener("resize", detect);
      window.removeEventListener("scroll", detect, true);
    };
  }, []);

  async function mutate(
    operation: (owner?: number) => Promise<Partial<Schema["NoteResponse"]>>,
    success: string,
  ): Promise<void> {
    if (!navigator.onLine) {
      setError("标注和阅读样式需要联网保存，请连接服务后重试。");
      throw new Error("offline");
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const owner = await readAccount().catch(() => undefined);
      const changes = await operation(owner?.user.id);
      const updated = { ...current.current, ...changes };
      current.current = updated;
      onChange(updated);
      // Keep the current note usable offline without putting writes in the offline queue.
      if (owner)
        await saveNotes(
          owner.generation,
          [updated],
          undefined,
          owner.revision,
        ).catch(() => undefined);
      setMessage(success);
    } catch (cause) {
      setError(errorMessage(cause));
      throw cause;
    } finally {
      setBusy(false);
    }
  }

  function closeSelection() {
    setSelection(null);
    window.getSelection()?.removeAllRanges();
  }
  async function create(payload: Schema["AnnotationCreate"]) {
    try {
      await mutate(async (owner) => {
        const item = await createAnnotation(note.id, payload, owner);
        return { annotations: [...(current.current.annotations ?? []), item] };
      }, "标注已保存。");
      closeSelection();
    } catch {
      /* Keep selected offsets and the draft available for retry. */
    }
  }
  async function update(item: Annotation, payload: Schema["AnnotationUpdate"]) {
    await mutate(async (owner) => {
      const updated = await updateAnnotation(item.id, payload, owner);
      return {
        annotations: (current.current.annotations ?? []).map((entry) =>
          entry.id === item.id ? updated : entry,
        ),
      };
    }, "标注已更新。");
  }
  async function remove(item: Annotation) {
    await mutate(async (owner) => {
      await deleteAnnotation(item.id, owner);
      return {
        annotations: (current.current.annotations ?? []).filter(
          (entry) => entry.id !== item.id,
        ),
      };
    }, "标注已删除。");
  }
  function jump(item: Annotation) {
    const element = surface.current?.querySelector<HTMLElement>(
      `[data-annotation-ids~="${item.id}"]`,
    );
    if (!element) {
      setError("原文位置暂不可用，请联网刷新笔记。");
      return;
    }
    for (
      let parent = element.parentElement;
      parent;
      parent = parent.parentElement
    ) {
      if (parent instanceof HTMLDetailsElement) parent.open = true;
    }
    element.scrollIntoView({ block: "center", behavior: "smooth" });
    element.animate(
      [{ outline: "3px solid #e99d24" }, { outline: "3px solid transparent" }],
      { duration: 1400 },
    );
  }
  async function saveStyle(patch: StylePatch, global: boolean) {
    await mutate(
      async (owner) =>
        global
          ? { reading_preferences: await saveReadingPreferences(patch, owner) }
          : { display_overrides: await saveDisplay(note.id, patch, owner) },
      "阅读样式已保存。",
    );
    setStyles(false);
  }
  async function resetStyle() {
    await mutate(async (owner) => {
      await resetDisplay(note.id, owner);
      return { display_overrides: {} };
    }, "本文已恢复跟随全局样式。");
    setStyles(false);
  }
  return (
    <section className="original-section note-reading">
      <div className="reading-heading">
        <h2>原始正文</h2>
        <div className="annotation-actions">
          <button
            className="inline-button"
            disabled={busy}
            onClick={() => {
              closeSelection();
              setError("");
              setStyles(true);
            }}
          >
            阅读样式
          </button>
          <button
            className="inline-button"
            aria-expanded={sidebar}
            onClick={() => {
              closeSelection();
              setSidebar(!sidebar);
            }}
          >
            我的标注（{annotations.length}）
          </button>
        </div>
      </div>
      <p className="reading-hint">
        选中一段正文可高亮或添加批注；修改需要联网，仅自己可见。
      </p>
      {selectionHint && (
        <p className="notice" role="status">
          {selectionHint}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {error && !selection && !styles && !sidebar && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <div className={`reading-layout${sidebar ? " with-annotations" : ""}`}>
        <div
          ref={surface}
          className="reading-surface"
          style={readingVariables(
            resolvedReadingStyle(
              note.reading_preferences,
              note.display_overrides,
            ),
          )}
        >
          <ArticleContent
            text={note.content.text}
            blocks={note.content.blocks}
            images={note.content.images}
            annotations={annotations}
            annotatable
          />
        </div>
        {sidebar && (
          <AnnotationSidebar
            annotations={annotations}
            busy={busy}
            error={error}
            onJump={jump}
            onUpdate={update}
            onDelete={remove}
            onClose={() => setSidebar(false)}
          />
        )}
      </div>
      {selection && !styles && (
        <AnnotationToolbar
          key={`${selection.block_index}:${selection.start_offset}:${selection.end_offset}`}
          selection={selection}
          position={position}
          busy={busy}
          error={error}
          onSave={create}
          onClose={closeSelection}
        />
      )}
      {styles && (
        <ReadingStyleSettings
          preferences={note.reading_preferences}
          overrides={note.display_overrides ?? {}}
          busy={busy}
          error={error}
          onSave={saveStyle}
          onReset={resetStyle}
          onClose={() => setStyles(false)}
        />
      )}
    </section>
  );
}
