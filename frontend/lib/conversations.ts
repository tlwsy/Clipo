// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, ApiError, type Schema } from "./api";

export type Message = Schema["ConversationMessage"];
export type ConversationJob = Schema["ConversationJobResponse"];
export type History = Schema["ConversationHistory"];

export function conversationPending(job: ConversationJob | null): boolean {
  return !!job && ["queued", "running", "retrying"].includes(job.status);
}

export function mergeMessages(
  previous: Message[],
  incoming: Message[],
): Message[] {
  const rows = new Map(
    previous.map((row) => [`${row.turn_index}:${row.role}`, row]),
  );
  for (const row of incoming) rows.set(`${row.turn_index}:${row.role}`, row);
  return [...rows.values()].sort(
    (a, b) =>
      a.turn_index - b.turn_index ||
      (a.role === b.role ? 0 : a.role === "user" ? -1 : 1),
  );
}

async function conversationRequest<T>(
  path: string,
  userId: number,
  signal: AbortSignal,
  options: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal.aborted) controller.abort();
  signal.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, 15000);
  try {
    return await api<T>(path, {
      ...options,
      expectedUserId: userId,
      signal: controller.signal,
    });
  } catch (cause) {
    if (controller.signal.aborted && !signal.aborted)
      throw new ApiError(
        0,
        "conversation_timeout",
        "请求超时，请刷新对话确认状态或重新发送同一问题。",
      );
    throw cause;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", abort);
  }
}

export function loadConversation(
  noteId: number,
  userId: number,
  signal: AbortSignal,
  before?: number,
): Promise<History> {
  return conversationRequest(
    `/notes/${noteId}/conversations${before === undefined ? "" : `?before=${before}`}`,
    userId,
    signal,
  );
}

export function askQuestion(
  noteId: number,
  userId: number,
  question: string,
  key: string,
  signal: AbortSignal,
): Promise<ConversationJob> {
  const body: Schema["ConversationRequest"] = { question, request_key: key };
  return conversationRequest(`/notes/${noteId}/conversations`, userId, signal, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function retryQuestion(
  jobId: string,
  userId: number,
  signal: AbortSignal,
): Promise<ConversationJob> {
  return conversationRequest(
    `/conversation-jobs/${jobId}/retry`,
    userId,
    signal,
    {
      method: "POST",
    },
  );
}
