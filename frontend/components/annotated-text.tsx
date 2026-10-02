// SPDX-License-Identifier: AGPL-3.0-or-later
import { Fragment, type ReactNode } from "react";
import type { Schema } from "@/lib/api";
import { articleUrl } from "@/lib/article";
import { annotationSegments, type Annotation } from "@/lib/annotations";

export function AnnotatedText({
  spans,
  text,
  annotations = [],
  blockIndex,
}: {
  spans?: Schema["ContentInline"][];
  text: string;
  annotations?: Annotation[];
  blockIndex?: number;
}) {
  const inlines: Schema["ContentInline"][] = spans?.length
    ? spans
    : [{ text, bold: false, italic: false, strike: false, code: false }];
  const source = inlines.map((span) => span.text).join("");
  const segments = annotationSegments(source, annotations);
  let offset = 0;
  const content = inlines.map((span, index) => {
    const start = offset;
    offset += span.text.length;
    const end = offset;
    let child: ReactNode = segments
      .filter((segment) => segment.start < end && segment.end > start)
      .map((segment) => {
        const value = source.slice(
          Math.max(start, segment.start),
          Math.min(end, segment.end),
        );
        return segment.annotations.length ? (
          <mark
            key={segment.start}
            className={`annotation-mark highlight-${segment.color ?? "none"}`}
            data-annotation-ids={segment.annotations
              .map((item) => item.id)
              .join(" ")}
            title={
              segment.annotations
                .map((item) => item.note_text)
                .filter(Boolean)
                .join("\n") || "高亮标注"
            }
          >
            {value}
          </mark>
        ) : (
          <Fragment key={segment.start}>{value}</Fragment>
        );
      });
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
  });
  return blockIndex === undefined ? (
    <>{content}</>
  ) : (
    <span data-annotation-block={blockIndex}>{content}</span>
  );
}
