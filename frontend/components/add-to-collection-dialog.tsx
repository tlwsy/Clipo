// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useState } from "react";
import { errorMessage } from "@/lib/api";
import {
  changeCollectionNotes,
  collectionColors,
  loadCollections,
  type Collection,
} from "@/lib/collections";
import { CollectionDialog } from "./collection-dialog";
import { CollectionCreateDialog } from "./collection-create-dialog";
import { Icon } from "./icon";

export function AddToCollectionDialog({
  noteIds,
  onClose,
  onSaved,
}: {
  noteIds: number[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [initial, setInitial] = useState<number[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const ids = noteIds.join(",");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setCollections([]);
    setError("");
    const notes = ids.split(",").map(Number);
    Promise.all([
      loadCollections(),
      notes.length === 1 ? loadCollections(notes[0]) : Promise.resolve([]),
    ])
      .then(([all, memberships]) => {
        if (active) {
          setCollections(all);
          const current = memberships.map((item) => item.id);
          setInitial(current);
          setSelected(current);
        }
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [ids, attempt]);
  async function save() {
    setBusy(true);
    setError("");
    try {
      // Track each completed request so a retry never undoes successful changes.
      for (const item of collections) {
        const included = selected.includes(item.id);
        if (included === initial.includes(item.id)) continue;
        await changeCollectionNotes(item.id, noteIds, !included);
        setInitial((previous) =>
          included
            ? [...previous, item.id]
            : previous.filter((id) => id !== item.id),
        );
      }
      onSaved();
    } catch (cause) {
      setError(
        `部分操作可能已保存，可重试完成剩余操作。${errorMessage(cause)}`,
      );
    } finally {
      setBusy(false);
    }
  }
  if (creating)
    return (
      <CollectionCreateDialog
        onClose={() => setCreating(false)}
        onSaved={(value) => {
          setCollections((previous) => [...previous, value]);
          setSelected((previous) => [...previous, value.id]);
          setCreating(false);
        }}
      />
    );
  return (
    <CollectionDialog
      title={noteIds.length === 1 ? "管理所属空间" : "添加到空间"}
      onClose={onClose}
      busy={busy}
    >
      <p>
        {noteIds.length === 1
          ? "勾选加入空间，取消勾选移出空间。"
          : `为已选 ${noteIds.length} 篇笔记添加空间，原有归属保持不变。`}
      </p>
      {loading ? (
        <p role="status">正在读取空间…</p>
      ) : (
        <>
          <label>
            搜索空间
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <div className="collection-options">
            {collections
              .filter((item) => item.name.includes(search))
              .map((item) => (
                <label className="checkbox-label" key={item.id}>
                  <input
                    type="checkbox"
                    disabled={busy}
                    checked={selected.includes(item.id)}
                    onChange={(event) =>
                      setSelected((previous) =>
                        event.target.checked
                          ? [...previous, item.id]
                          : previous.filter((id) => id !== item.id),
                      )
                    }
                  />
                  <Icon
                    name={item.icon ?? "folder"}
                    style={{ color: collectionColors[item.color].value }}
                  />
                  {item.name}
                </label>
              ))}
          </div>
          {!collections.length && <p>还没有空间，可以先创建一个。</p>}
          <div className="collection-actions">
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => setCreating(true)}
            >
              创建空间
            </button>
            <button
              className="button"
              disabled={busy || !collections.length}
              onClick={save}
            >
              {busy ? "正在保存…" : "保存归属"}
            </button>
          </div>
        </>
      )}
      {error && (
        <p role="alert" className="notice error">
          {error}
          <button
            className="inline-button"
            disabled={busy}
            onClick={() => setAttempt((previous) => previous + 1)}
          >
            重新加载
          </button>
        </p>
      )}
    </CollectionDialog>
  );
}
