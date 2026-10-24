import { useI18n } from "@/lib/i18n";
import type { LibraryDraft } from "@/components/ai-library";

const labels: Record<string, string> = {
  read_sources: "Read project sources", read_database: "Read the business database",
  read_attachments: "Read attachments", read_web: "Read official web sources", structured_output: "Produce structured results",
};

export function SkillMetadata({ definition }: { definition: LibraryDraft }) {
  const { t } = useI18n();
  return <div className="mt-5 space-y-2 rounded-md bg-muted p-3 text-sm" aria-label={t("Calculated skill metadata")}>
    <p>{t("All supported assistants")}: ChatGPT / Codex, Claude Code</p>
    <p>{t("Required capabilities")}: {definition.required_capabilities.length ? definition.required_capabilities.map(value => t(labels[value] || value)).join(", ") : t("Calculated when saved")}</p>
    <p className="text-xs muted">{t("Capabilities are calculated from the procedure and remain informational. They never grant access.")}</p>
  </div>;
}
