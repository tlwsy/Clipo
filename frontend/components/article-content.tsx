// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { Fragment, useState, type ReactNode } from "react";
import type { Schema } from "@/lib/api";
import {
  articleImages,
  articleUrl,
  steamCardUrl,
  type ArticleBlock,
} from "@/lib/article";

function InlineText({
  spans,
  text,
}: {
  spans?: Schema["ContentInline"][];
  text: string;
}) {
  if (!spans?.length) return <>{text}</>;
  return (
    <>
      {spans.map((span, index) => {
        let child: ReactNode = span.text;
        if (span.code) child = <code>{child}</code>;
        if (span.bold) child = <strong>{child}</strong>;
        if (span.italic) child = <em>{child}</em>;
        if (span.strike) child = <del>{child}</del>;
        const url = articleUrl(span.url);
        if (url)
          child = (
            <a href={url} target="_blank" rel="noreferrer noopener">
              {child}
            </a>
          );
        return <Fragment key={index}>{child}</Fragment>;
      })}
    </>
  );
}

function ArticleImage({
  url,
  alt,
  width,
  height,
  loadImages,
  cover = false,
}: {
  url: string;
  alt: string;
  width?: number | null;
  height?: number | null;
  loadImages: boolean;
  cover?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const safe = articleUrl(url);
  if (!safe) return <span className="muted">图片链接不可用</span>;
  if (!loadImages || failed)
    return (
      <a
        className="article-image-fallback"
        href={safe}
        target="_blank"
        rel="noreferrer noopener"
      >
        {failed
          ? "图片暂时无法加载，打开原图 ↗"
          : cover
            ? "查看封面 ↗"
            : "查看原图 ↗"}
      </a>
    );
  return (
    <a
      className={cover ? "game-card-cover" : "article-image-link"}
      href={safe}
      target="_blank"
      rel="noreferrer noopener"
      aria-label={cover ? "查看游戏封面" : "打开原图"}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- captured external URLs remain statically exportable */}
      <img
        src={safe}
        alt={alt}
        width={width ?? undefined}
        height={height ?? undefined}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    </a>
  );
}

function GameCard({
  block,
  loadImages,
}: {
  block: ArticleBlock;
  loadImages: boolean;
}) {
  const steam = steamCardUrl(block);
  return (
    <aside
      className="game-card"
      aria-label={`游戏卡片：${block.text || "未识别游戏"}`}
    >
      {block.image ? (
        <ArticleImage url={block.image} alt="" loadImages={loadImages} cover />
      ) : (
        <div className="game-card-placeholder" aria-hidden="true">
          游戏
        </div>
      )}
      <div className="game-card-info">
        <span className="game-card-store">
          {block.store === "steam"
            ? "STEAM"
            : block.store === "epic"
              ? "EPIC GAMES"
              : "原文游戏卡片"}
        </span>
        <strong>{block.text || "未识别游戏"}</strong>
        {steam ? (
          <a
            className="game-card-action"
            href={steam}
            target="_blank"
            rel="noreferrer noopener"
          >
            在 Steam 查看 <span aria-hidden="true">↗</span>
          </a>
        ) : (
          <span className="muted">
            {block.store === "epic"
              ? "原文为 Epic 卡片，保留名称与封面"
              : "商店链接暂未确认，可查看原网页"}
          </span>
        )}
      </div>
    </aside>
  );
}

function Blocks({
  blocks,
  loadImages,
  depth = 0,
}: {
  blocks: ArticleBlock[];
  loadImages: boolean;
  depth?: number;
}) {
  if (depth > 16) return <p className="notice">内容层级过深，请查看原网页。</p>;
  return (
    <>
      {blocks.map((block, index) => {
        const body = <InlineText spans={block.inlines} text={block.text} />;
        const children = (
          <Blocks
            blocks={block.children ?? []}
            loadImages={loadImages}
            depth={depth + 1}
          />
        );
        switch (block.type) {
          case "heading": {
            const Tag = `h${Math.min(6, Math.max(2, block.level || 2))}` as
              "h2" | "h3" | "h4" | "h5" | "h6";
            return <Tag key={index}>{body}</Tag>;
          }
          case "image":
            return (
              <figure key={index}>
                {block.url && (
                  <ArticleImage
                    url={block.url}
                    alt={block.alt || "原文图片"}
                    width={block.width}
                    height={block.height}
                    loadImages={loadImages}
                  />
                )}
                {block.alt && <figcaption>{block.alt}</figcaption>}
              </figure>
            );
          case "game_card":
            return (
              <GameCard key={index} block={block} loadImages={loadImages} />
            );
          case "quote":
            return (
              <blockquote key={index}>
                {body}
                {children}
              </blockquote>
            );
          case "code":
            return (
              <pre key={index}>
                <code>{block.text}</code>
              </pre>
            );
          case "list":
            return block.ordered ? (
              <ol key={index}>{children}</ol>
            ) : (
              <ul key={index}>{children}</ul>
            );
          case "list_item":
            return (
              <li key={index}>
                {body}
                {children}
              </li>
            );
          case "table":
            return (
              <div
                className="article-table"
                key={index}
                tabIndex={0}
                role="region"
                aria-label="原文表格"
              >
                <table>
                  <tbody>{children}</tbody>
                </table>
              </div>
            );
          case "table_row":
            return <tr key={index}>{children}</tr>;
          case "table_cell":
            return block.header ? (
              <th key={index} scope="col">
                {body}
                {children}
              </th>
            ) : (
              <td key={index}>
                {body}
                {children}
              </td>
            );
          case "details":
            return (
              <details key={index}>
                <summary>{block.text || "展开内容"}</summary>
                {children}
              </details>
            );
          case "divider":
            return <hr key={index} />;
          default:
            return (
              <p className="article-paragraph" key={index}>
                {body}
              </p>
            );
        }
      })}
    </>
  );
}

export function ArticleContent({
  text,
  blocks = [],
  images = [],
  publicView = false,
}: {
  text: string;
  blocks?: ArticleBlock[];
  images?: string[];
  publicView?: boolean;
}) {
  const [loadImages, setLoadImages] = useState(!publicView);
  const included = articleImages(blocks);
  const extraImages = images.filter((url) => !included.has(url));
  return (
    <div className="article-content">
      {publicView &&
        !loadImages &&
        (included.size > 0 || images.length > 0) && (
          <div className="article-media-notice">
            <p>图片来自原网站，加载时会连接外部图片服务。</p>
            <button
              type="button"
              className="inline-button"
              onClick={() => setLoadImages(true)}
            >
              加载原文图片
            </button>
          </div>
        )}
      {blocks.length ? (
        <Blocks blocks={blocks} loadImages={loadImages} />
      ) : (
        <div className="original-text">{text || "这篇内容没有文字正文。"}</div>
      )}
      {extraImages.length > 0 && (
        <div className="article-gallery" aria-label="原文图片">
          {extraImages.map((url, index) => (
            <figure key={`${index}-${url}`}>
              <ArticleImage
                url={url}
                alt={`原文图片 ${index + 1}`}
                loadImages={loadImages}
              />
            </figure>
          ))}
        </div>
      )}
    </div>
  );
}
