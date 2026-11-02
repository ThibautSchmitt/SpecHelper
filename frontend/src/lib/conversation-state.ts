import type { RequestItem } from "@/lib/api";

export const conversationLabels = {
  DISCUSSION: "In discussion", IN_PROGRESS: "In progress", WAITING_AI: "Waiting for AI", AWAITING_REPLY: "Reply expected",
};
export function conversationState(value: RequestItem) {
  // Older API fixtures/bookmarks retain their technical states. Current responses
  // always carry the state derived from actual jobs, rather than this fallback.
  return value.conversation_state || (value.status === "NEEDS_CLARIFICATION" ? "AWAITING_REPLY" :
    ["QUEUED", "UNDERSTANDING", "ANALYZING", "REVIEWING", "GENERATING_RESULT", "CONTINUING_CONVERSATION", "GENERATING_TICKET"].includes(value.status) ? "IN_PROGRESS" : "DISCUSSION");
}
