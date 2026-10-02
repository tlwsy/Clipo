// SPDX-License-Identifier: AGPL-3.0-or-later
import Markdown from "react-markdown";
import type { Message } from "@/lib/conversations";

export function ConversationMessage({
  message,
  unanswered = false,
}: {
  message: Message;
  unanswered?: boolean;
}) {
  return (
    <li className={`conversation-message ${message.role}`}>
      <div className="conversation-meta">
        <strong>{message.role === "user" ? "我" : "AI"}</strong>
        <time dateTime={message.created_at}>
          {new Date(message.created_at).toLocaleString("zh-CN")}
        </time>
      </div>
      {message.role === "user" ? (
        <p className="conversation-question">{message.content}</p>
      ) : (
        <div className="markdown">
          <Markdown
            skipHtml
            disallowedElements={["img"]}
            components={{
              a: ({ children, href }) =>
                href && /^https?:\/\//i.test(href) ? (
                  <a href={href} target="_blank" rel="noreferrer noopener">
                    {children}
                  </a>
                ) : (
                  <span>{children}</span>
                ),
            }}
          >
            {message.content}
          </Markdown>
        </div>
      )}
      {unanswered && <small className="muted">这条问题尚无回答</small>}
    </li>
  );
}
