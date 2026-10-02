// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { errorMessage } from "@/lib/api";
import {
  loadCollections,
  deleteCollection,
  type Collection,
} from "@/lib/collections";
import { CollectionList } from "@/components/collection-list";
import { CollectionDetailView } from "@/components/collection-detail-view";
import { CollectionCreateDialog } from "@/components/collection-create-dialog";
import { CollectionDialog } from "@/components/collection-dialog";

function Collections() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Collection | "new" | null>(null);
  const [deleting, setDeleting] = useState<Collection | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const refresh = useCallback(async () => {
    try {
      setCollections(await loadCollections());
      setError("");
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, []);
  useEffect(() => {
    let active = true;
    loadCollections()
      .then((items) => {
        if (active) setCollections(items);
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
  }, []);
  const current = collections.find((item) => String(item.id) === id);
  const askDelete = (item: Collection) => {
    setDeleteError("");
    setDeleting(item);
  };
  return (
    <>
      {error && (
        <p className="notice error" role="alert">
          {error}
          <button className="inline-button" onClick={refresh}>
            重试
          </button>
        </p>
      )}
      {loading ? (
        <p role="status">正在读取空间…</p>
      ) : id ? (
        current ? (
          <CollectionDetailView
            key={current.id}
            collection={current}
            onEdit={() => setEditing(current)}
            onDelete={() => askDelete(current)}
            onChanged={refresh}
          />
        ) : (
          <section className="empty-state">
            <h1>空间不存在或无法读取</h1>
            <Link href="/collections/">返回空间列表</Link>
          </section>
        )
      ) : (
        <>
          <div className="page-heading">
            <div>
              <span className="eyebrow">COLLECTIONS</span>
              <h1>空间</h1>
              <p>按主题组织笔记，一篇笔记可以属于多个空间。</p>
            </div>
            <button className="button" onClick={() => setEditing("new")}>
              创建空间
            </button>
          </div>
          {!collections.length && !error && (
            <section className="empty-state">
              <h2>创建你的第一个空间</h2>
              <p>未分配的笔记仍在“全部笔记”中。</p>
            </section>
          )}
          <CollectionList
            collections={collections}
            onEdit={setEditing}
            onDelete={askDelete}
          />
        </>
      )}
      {editing && (
        <CollectionCreateDialog
          collection={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={(value) => {
            setCollections((previous) =>
              previous.some((item) => item.id === value.id)
                ? previous.map((item) => (item.id === value.id ? value : item))
                : [...previous, value],
            );
            setEditing(null);
          }}
        />
      )}
      {deleting && (
        <CollectionDialog
          title="删除空间"
          onClose={() => setDeleting(null)}
          busy={busy}
        >
          <p>确认删除“{deleting.name}”？空间归属会移除，其中的笔记会保留。</p>
          {deleteError && (
            <p role="alert" className="notice error">
              {deleteError}
            </p>
          )}
          <button
            className="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setDeleteError("");
              try {
                await deleteCollection(deleting.id);
                setCollections((previous) =>
                  previous.filter((item) => item.id !== deleting.id),
                );
                if (id === String(deleting.id)) router.push("/collections/");
                setDeleting(null);
              } catch (cause) {
                setDeleteError(errorMessage(cause));
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "正在删除…" : "确认删除空间"}
          </button>
        </CollectionDialog>
      )}
    </>
  );
}
export default function CollectionsPage() {
  return (
    <Suspense fallback={<p role="status">正在打开空间…</p>}>
      <Collections />
    </Suspense>
  );
}
