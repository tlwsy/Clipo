// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, type Schema } from "@/lib/api";
import {
  changeCollectionNotes,
  collectionColors,
  type Collection,
} from "@/lib/collections";
import { Icon } from "./icon";
import { NoteCard } from "./note-card";
import { CollectionNotePicker } from "./collection-note-picker";

export function CollectionDetailView({
  collection,
  onEdit,
  onDelete,
  onChanged,
}: {
  collection: Collection;
  onEdit: () => void;
  onDelete: () => void;
  onChanged: () => Promise<void>;
}) {
  const [items, setItems] = useState<Schema["NoteItem"][]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const generation = useRef(0);
  const load = useCallback(
    async (next?: string) => {
      const current = ++generation.current;
      setBusy(true);
      setError("");
      try {
        const page = await api<Schema["NotePage"]>(
          `/collections/${collection.id}/notes?limit=24${next ? `&cursor=${encodeURIComponent(next)}` : ""}`,
        );
        if (current !== generation.current) return;
        setItems((previous) =>
          next ? [...previous, ...page.items] : page.items,
        );
        setCursor(page.next_cursor);
      } catch (cause) {
        if (current === generation.current) setError(errorMessage(cause));
      } finally {
        if (current === generation.current) setBusy(false);
      }
    },
    [collection.id],
  );
  useEffect(() => {
    const requests = generation;
    void load();
    return () => {
      requests.current++;
    };
  }, [load]);
  return (
    <>
      <Link className="text-link" href="/collections/">
        返回空间列表
      </Link>
      <div className="page-heading">
        <div>
          <span
            className="collection-symbol"
            style={{ color: collectionColors[collection.color].value }}
          >
            <Icon name={collection.icon ?? "folder"} size={28} />
          </span>
          <h1>{collection.name}</h1>
          <p>{collection.note_count} 篇笔记</p>
        </div>
        <div className="collection-actions">
          <button
            className="button"
            disabled={busy}
            onClick={() => setAdding(true)}
          >
            添加笔记
          </button>
          <button className="button secondary" onClick={onEdit}>
            编辑空间
          </button>
          <button className="inline-button danger" onClick={onDelete}>
            删除空间
          </button>
        </div>
      </div>
      {error && (
        <p role="alert" className="notice error">
          {error}
          <button className="inline-button" onClick={() => load()}>
            重试
          </button>
        </p>
      )}
      {!busy && !error && !items.length && (
        <section className="empty-state">
          <h2>这个空间还没有笔记</h2>
          <p>点击“添加笔记”，或在全部笔记中多选添加。</p>
        </section>
      )}
      <div className="notes-grid">
        {items.map((note) => (
          <NoteCard
            key={note.id}
            note={note}
            disabled={busy}
            onRemove={async () => {
              setBusy(true);
              setError("");
              try {
                await changeCollectionNotes(collection.id, [note.id], true);
                await onChanged();
                await load();
              } catch (cause) {
                setError(errorMessage(cause));
              } finally {
                setBusy(false);
              }
            }}
          />
        ))}
      </div>
      {busy && <p role="status">正在读取笔记…</p>}
      {cursor && (
        <button
          className="button secondary load-more"
          disabled={busy}
          onClick={() => load(cursor)}
        >
          加载更多
        </button>
      )}
      {adding && (
        <CollectionNotePicker
          collection={collection}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            void onChanged();
            void load();
          }}
        />
      )}
    </>
  );
}
