// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import React from "react";
import type { Schema } from "../lib/api";
import { commentThreads } from "../lib/comments";

type Comment = Schema["CommentResponse"];

export function NoteComments({ note }: { note: Schema["NoteResponse"] }) {
  const valuable = note.comments.filter((comment) => comment.is_valuable);
  const unscored = note.comments.filter((comment) => comment.ai_score === null);
  const hidden = note.comments.length - valuable.length - unscored.length;
  const renderComment = (comment: Comment) => {
    const parent = note.comments.find(
      (row) => row.source_id && row.source_id === comment.parent_source_id,
    );
    return (
      <div
        className="comment"
        id={`comment-${comment.position}`}
        key={comment.id}
      >
        <div className="comment-heading">
          <strong>{comment.author || "匿名"}</strong>
          {comment.is_valuable && <span className="pill">优质评论</span>}
          <small>{comment.likes} 赞</small>
        </div>
        {comment.parent_source_id && (
          <small className="muted">回复 {parent?.author || "原评论"}</small>
        )}
        <p className="comment-text">{comment.content}</p>
        <small className="muted">
          {comment.ai_score === null
            ? "尚未评分"
            : `AI 评分 ${Math.round(comment.ai_score * 100)} / 100`}
          {comment.ai_reason ? ` · ${comment.ai_reason}` : ""}
        </small>
      </div>
    );
  };
  return (
    <section className="original-section">
      <h2>评论精华</h2>
      <p className="muted">
        已采集 {note.comments.length} 条（含回复），{valuable.length} 条优质评论
        {hidden > 0 && `，已隐藏 ${hidden} 条非优质评论`}。
        {note.content.comment_capture_limit === 0
          ? "本次已关闭评论采集。"
          : "受平台和采集上限影响，讨论可能不完整。"}
      </p>
      {note.content.comment_capture_limit != null &&
        note.content.comment_capture_limit > 0 && (
          <p className="muted">
            本次评论采集上限：{note.content.comment_capture_limit}{" "}
            条（含回复）。
          </p>
        )}
      {note.comment_score_error && (
        <p className="notice" role="status">
          {note.comment_score_error}
        </p>
      )}
      {(note.comment_insights ?? []).length > 0 && (
        <div className="comment-insights">
          <h3>AI 评论精华</h3>
          <p className="muted">依据优质评论整合；评论观点不代表已核实事实。</p>
          <ul>
            {note.comment_insights!.map((insight, index) => (
              <li key={index}>
                <p>{insight.text}</p>
                <small>
                  来源：
                  {insight.indices.map((position, index) => (
                    <a
                      className="comment-source"
                      href={`#comment-${position}`}
                      key={`${position}-${index}`}
                    >
                      评论 {position + 1}
                    </a>
                  ))}
                </small>
              </li>
            ))}
          </ul>
        </div>
      )}
      <h3>优质讨论</h3>
      {valuable.length === 0 && (
        <p className="muted">
          {unscored.length
            ? "暂无已评为优质的评论，未评分内容保留在下方。"
            : "本次暂无达到评分阈值的评论。"}
        </p>
      )}
      {valuable.length > 0 && !(note.comment_insights ?? []).length && (
        <p className="muted">
          尚未生成评论精华，可重新生成摘要以整理已保存评论。
        </p>
      )}
      {commentThreads(valuable, note.comments).map((thread) => (
        <div className="comment-thread" key={thread[0].id}>
          {thread.map(renderComment)}
        </div>
      ))}
      {unscored.length > 0 && (
        <details className="unscored-comments">
          <summary>未评分评论（{unscored.length}）</summary>
          <p className="muted">
            未评分不代表低价值；可能受候选数量、输入长度或模型可用性限制。
          </p>
          {unscored.map(renderComment)}
        </details>
      )}
    </section>
  );
}
