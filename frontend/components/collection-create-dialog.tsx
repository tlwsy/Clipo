// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useState } from "react";
import { errorMessage, type Schema } from "@/lib/api";
import {
  collectionColors,
  collectionIcons,
  saveCollection,
  type Collection,
} from "@/lib/collections";
import { CollectionDialog } from "./collection-dialog";

export function CollectionCreateDialog({
  collection,
  onClose,
  onSaved,
}: {
  collection?: Collection;
  onClose: () => void;
  onSaved: (value: Collection) => void;
}) {
  const [name, setName] = useState(collection?.name ?? "");
  const [color, setColor] = useState<Collection["color"]>(
    collection?.color ?? "blue",
  );
  const [icon, setIcon] = useState<NonNullable<Collection["icon"]> | "">(
    collection?.icon ?? "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <CollectionDialog
      title={collection ? "编辑空间" : "创建空间"}
      onClose={onClose}
      busy={busy}
    >
      <form
        className="collection-form"
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            onSaved(
              await saveCollection(
                {
                  name: name.trim(),
                  color,
                  icon: icon || null,
                } satisfies Schema["CollectionCreate"],
                collection?.id,
              ),
            );
          } catch (cause) {
            setError(errorMessage(cause));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          空间名称
          <input
            autoFocus
            required
            maxLength={100}
            value={name}
            onChange={(event) => setName(event.target.value)}
            disabled={busy}
          />
        </label>
        <fieldset disabled={busy}>
          <legend>颜色</legend>
          <div className="collection-colors">
            {Object.entries(collectionColors).map(([value, item]) => (
              <label key={value} title={item.label}>
                <input
                  type="radio"
                  name="collection-color"
                  value={value}
                  checked={color === value}
                  onChange={() => setColor(value as Collection["color"])}
                />
                <span style={{ background: item.value }} aria-hidden="true" />
                {item.label}
              </label>
            ))}
          </div>
        </fieldset>
        <label>
          图标
          <select
            aria-label="图标"
            value={icon}
            disabled={busy}
            onChange={(event) => setIcon(event.target.value as typeof icon)}
          >
            <option value="">无图标</option>
            {Object.entries(collectionIcons).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        <button className="button" disabled={busy || !name.trim()}>
          {busy ? "正在保存…" : "保存空间"}
        </button>
      </form>
    </CollectionDialog>
  );
}
