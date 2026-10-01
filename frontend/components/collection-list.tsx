// SPDX-License-Identifier: AGPL-3.0-or-later
import Link from "next/link";
import { collectionColors, type Collection } from "@/lib/collections";
import { Icon } from "./icon";

export function CollectionList({
  collections,
  onEdit,
  onDelete,
}: {
  collections: Collection[];
  onEdit: (value: Collection) => void;
  onDelete: (value: Collection) => void;
}) {
  return (
    <div className="notes-grid">
      {collections.map((collection) => (
        <article className="note-card collection-card" key={collection.id}>
          <Link href={`/collections/?id=${collection.id}`}>
            <span
              className="collection-symbol"
              style={{ color: collectionColors[collection.color].value }}
            >
              <Icon name={collection.icon ?? "folder"} size={28} />
            </span>
            <h2>{collection.name}</h2>
            <p>{collection.note_count} 篇笔记</p>
          </Link>
          <div className="collection-actions">
            <button
              className="inline-button"
              onClick={() => onEdit(collection)}
              aria-label={`编辑空间 ${collection.name}`}
            >
              编辑
            </button>
            <button
              className="inline-button danger"
              onClick={() => onDelete(collection)}
              aria-label={`删除空间 ${collection.name}`}
            >
              删除
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
