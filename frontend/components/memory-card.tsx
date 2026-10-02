// SPDX-License-Identifier: AGPL-3.0-or-later
import Link from "next/link";
import type { MemoryNote } from "@/lib/memory";
import { sourceName } from "@/lib/source-name";

export function MemoryCard({ note }: { note: MemoryNote }) {
  return (
    <>
      <div className="memory-meta">
        <span>{sourceName(note)}</span>
        <time dateTime={note.created_at}>
          {new Date(note.created_at).toLocaleDateString("zh-CN")} 保存
        </time>
      </div>
      <Link
        className="memory-reading-link"
        href={`/notes/?id=${note.id}`}
        prefetch={false}
      >
        <h2>{note.title || "无标题笔记"}</h2>
        <p className="memory-snippet">
          {note.summary_snippet || "打开原文，重拾当时的想法。"}
        </p>
        {note.key_points.length > 0 && (
          <ul className="memory-points">
            {note.key_points.map((point, index) => (
              <li key={index}>{point}</li>
            ))}
          </ul>
        )}
      </Link>
      <div className="memory-reasons" aria-label="推荐理由">
        {note.has_summary && <span className="pill">留有 AI 摘要</span>}
        {note.annotations_count > 0 && (
          <span className="pill">{note.annotations_count} 处私人标注</span>
        )}
        {!note.has_summary && note.annotations_count === 0 && (
          <span className="pill">曾认真读过</span>
        )}
      </div>
    </>
  );
}
