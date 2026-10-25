export const assistantProviders = [
  { id: "codex", name: "ChatGPT / Codex" },
  { id: "claude", name: "Claude Code" },
  { id: "antigravity", name: "Antigravity" },
] as const;

export type AssistantProvider = (typeof assistantProviders)[number]["id"];

export function assistantName(provider?: string | null): string {
  return assistantProviders.find((item) => item.id === provider)?.name || provider || "Recorded AI";
}
