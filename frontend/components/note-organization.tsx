"use client";
import { useState, type FormEvent } from "react";
import { changeNote, loadNote } from "@/lib/notes";
import { api, errorMessage, type Schema } from "@/lib/api";

export function NoteOrganization({
  note,
  onChange,
}: {
  note: Schema["NoteResponse"];
  onChange: (note: Schema["NoteResponse"]) => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function update(path: string, method: string, body?: object) {
    setBusy(true);
    setError("");
    try {
      if (method === "PATCH")
        await changeNote(note.id, "PATCH", { is_favorite: !note.is_favorite });
      else
        await api(path, {
          method,
          body: body ? JSON.stringify(body) : undefined,
        });
      onChange(await loadNote(note.id));
      setName("");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  function add(event: FormEvent) {
    event.preventDefault();
    if (name.trim())
      void update(`/notes/${note.id}/tags`, "POST", { name: name.trim() });
  }
  return (
    <section className="note-organization" aria-label="笔记整理">
      <button
        className="button secondary small"
        disabled={busy}
        aria-pressed={note.is_favorite}
        onClick={() =>
          update(`/notes/${note.id}`, "PATCH", {
            is_favorite: !note.is_favorite,
          })
        }
      >
        {note.is_favorite ? "★ 已收藏" : "☆ 标记收藏"}
      </button>
      <div className="tag-list">
        {note.tags.map((tag) => (
          <span className="subtle-badge" key={tag.id}>
            {tag.name}
            <button
              className="inline-button"
              disabled={busy}
              aria-label={`移除标签 ${tag.name}`}
              onClick={() =>
                update(`/notes/${note.id}/tags/${tag.id}`, "DELETE")
              }
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <form className="tag-form" onSubmit={add}>
        <label className="sr-only" htmlFor="new-tag">
          添加标签
        </label>
        <input
          id="new-tag"
          maxLength={50}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="添加标签"
        />
        <button
          className="button secondary small"
          disabled={busy || !name.trim()}
        >
          添加
        </button>
      </form>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
