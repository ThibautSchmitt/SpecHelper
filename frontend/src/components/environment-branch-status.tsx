"use client";

import { ArrowDownToLine, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Environment } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function EnvironmentSyncBadge({ value }: { value: Environment }) {
  const { t } = useI18n();
  const operation = ({ PENDING: "Update scheduled", SYNCING: "Updating", ERROR: "Update failed" } as Record<string, string>)[value.status];
  const state = value.git_sync_status || "UNKNOWN";
  const label = ({ SYNCED: "Up to date", PARTIAL: "Partially up to date", OUTDATED: "Update needed", UNKNOWN: "Branch status not verified" } as Record<string, string>)[state];
  return <span className="badge environment-update-badge" data-state={operation ? value.status : state === "SYNCED" ? "READY" : state === "PARTIAL" ? "PARTIAL" : state === "OUTDATED" ? "ERROR" : "UNKNOWN"}>
    {t(operation || label)}
    {value.git_check_running && !operation && <LoaderCircle size={12} className="animate-spin" aria-label={t("Checking branches…")} />}
  </span>;
}

export function EnvironmentBranchStatus({ environment, repository, disabled, onUpdate }: {
  environment: Environment;
  repository: Environment["repositories"][number];
  disabled: boolean;
  onUpdate: () => void;
}) {
  const { t, dateLocale } = useI18n();
  const value = repository.git_status;
  const state = value?.status || "UNKNOWN";
  const update = ["BEHIND", "AHEAD", "DIVERGED", "UNINITIALIZED"].includes(state);
  const label = state === "BEHIND" ? t(value?.behind === 1 ? "1 commit behind" : "{count} commits behind", { count: value?.behind || 0 })
    : t(({ CURRENT: "Up to date", DIVERGED: "Remote history changed", AHEAD: "Remote history changed", MISSING: "Remote branch not found", UNAVAILABLE: "Branch verification unavailable", UNINITIALIZED: "Update needed" } as Record<string, string>)[state] || (environment.git_check_running ? "Checking branches…" : "Branch status not verified"));
  return <div className="grid w-full grid-cols-[minmax(0,1fr)_2.75rem] items-center gap-2" data-branch-update-row>
    <div className="min-w-0">
      <span>{repository.branch}</span>
      <small className="muted block text-xs" title={value?.checked_at ? `${t("Last checked")}: ${new Date(value.checked_at).toLocaleString(dateLocale)}` : undefined}>{label}</small>
    </div>
    {update && <Button type="button" variant="ghost" size="sm" className="icon-action justify-self-end" disabled={disabled}
      aria-label={t("Update {repository} · {branch}", { repository: repository.path || repository.repository, branch: repository.branch })}
      title={t("Update branch")} onClick={onUpdate}><ArrowDownToLine size={15} aria-hidden="true" /></Button>}
  </div>;
}
