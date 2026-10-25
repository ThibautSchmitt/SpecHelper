import { Github, Gitlab, Ticket } from "lucide-react";
import { AssistantLogo } from "@/components/assistant-logo";

// Bundled Lucide marks retain their existing ISC notice. Platforms without a
// bundled redistributable mark use a neutral icon beside their visible name.
export function ProviderLogo({ provider }: { provider?: string | null }) {
  if (provider === "codex" || provider === "claude" || provider === "antigravity") return <AssistantLogo agent={provider} />;
  const Icon = provider === "github" ? Github : provider === "gitlab" ? Gitlab : Ticket;
  return <Icon size={18} className="shrink-0" data-provider={provider || "unknown"} aria-hidden="true" focusable="false" />;
}
