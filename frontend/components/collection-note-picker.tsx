// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, type Schema } from "@/lib/api";
import { changeCollectionNotes, type Collection } from "@/lib/collections";
import { CollectionDialog } from "./collection-dialog";

export function CollectionNotePicker({
  collection,
  onClose,
  onSaved,
}: {
  collection: Collection;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [items, setItems] = useState<Schema["NoteItem"][]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const load = useCallback(
    async (next?: string) => {
      const current = ++generation.current;
      setLoading(true);
      setError("");
      try {
        const page = await api<Schema["NotePage"]>(
          `/notes?limit=24&q=${encodeURIComponent(query)}${next ? `&cursor=${encodeURIComponent(next)}` : ""}`,
        );
        if (current !== generation.current) return;
        setItems((previous) =>
          next ? [...previous, ...page.items] : page.items,
        );
        setCursor(page.next_cursor);
      } catch (cause) {
        if (current === generation.current) setError(errorMessage(cause));
      } finally {
        if (current === generation.current) setLoading(false);
      }
    },
    [query],
  );
  useEffect(() => {
    const requests = generation;
    void load();
    return () => {
      requests.current++;
    };
  }, [load]);
  return (
    <CollectionDialog
      title={`添加笔记到 ${collection.name}`}
      onClose={onClose}
      busy={busy}
    >
      <p>每次最多选择 100 篇；已在空间中的笔记不会重复添加。</p>
      <form
        className="search-form"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(draft.trim());
        }}
      >
        <input
          aria-label="搜索可添加的笔记"
          type="search"
          maxLength={200}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button className="button secondary small" disabled={loading || busy}>
          搜索
        </button>
      </form>
      <div className="collection-options">
        {items.map((item) => (
          <label className="checkbox-label" key={item.id}>
            <input
              type="checkbox"
              checked={selected.includes(item.id)}
              disabled={
                busy || (!selected.includes(item.id) && selected.length >= 100)
              }
              onChange={(event) =>
                setSelected((previous) =>
                  event.target.checked
                    ? [...previous, item.id]
                    : previous.filter((id) => id !== item.id),
                )
              }
            />
            {item.title || "无标题笔记"}
          </label>
        ))}
      </div>
      {loading && <p role="status">正在读取笔记…</p>}
      {!loading && !items.length && !error && <p>没有符合条件的笔记。</p>}
      {cursor && (
        <button
          className="inline-button"
          disabled={loading || busy}
          onClick={() => load(cursor)}
        >
          加载更多笔记
        </button>
      )}
      {error && (
        <p role="alert" className="notice error">
          {error}
          <button
            className="inline-button"
            disabled={loading || busy}
            onClick={() => load()}
          >
            重试读取
          </button>
        </p>
      )}
      <div className="collection-actions">
        <span>已选 {selected.length} 篇</span>
        <button
          className="button"
          disabled={busy || !selected.length}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await changeCollectionNotes(collection.id, selected);
              onSaved();
            } catch (cause) {
              setError(errorMessage(cause));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "正在添加…" : "添加所选笔记"}
        </button>
      </div>
    </CollectionDialog>
  );
}
