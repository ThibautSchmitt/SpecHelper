"use client";

import { ArrowDownToLine, Check, CheckCircle2, ChevronDown, CircleHelp, Clipboard, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
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
  const { t } = useI18n();
  const value = repository.git_status;
  const state = value?.status || "UNKNOWN";
  const update = ["BEHIND", "AHEAD", "DIVERGED", "UNINITIALIZED"].includes(state);
  const label = state === "BEHIND" ? t(value?.behind === 1 ? "1 commit behind" : "{count} commits behind", { count: value?.behind || 0 })
    : t(({ CURRENT: "Up to date", DIVERGED: "Remote history changed", AHEAD: "Remote history changed", MISSING: "Remote branch not found", UNAVAILABLE: "Unknown state", UNINITIALIZED: "Update needed" } as Record<string, string>)[state] || "Unknown state");
  return <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3" data-branch-update-row>
    <span className="flex min-w-0 items-center gap-2 text-sm font-medium" title={environment.git_check_running?t("Checking branches…"):["UNKNOWN","UNAVAILABLE"].includes(state)?t("The remote state is unavailable or needs a new check."):undefined}>
      {state==="CURRENT"?<CheckCircle2 size={15} className="shrink-0 text-[var(--success)]" aria-hidden="true"/>:["UNKNOWN","UNAVAILABLE","MISSING"].includes(state)?<CircleHelp size={15} className="shrink-0 muted" aria-hidden="true"/>:null}
      {label}
    </span>
    {update && <Button type="button" variant="outline" size="sm" className="justify-self-end" disabled={disabled}
      aria-label={t("Update {repository} · {branch}", { repository: repository.path || repository.repository, branch: repository.branch })}
      title={t("Update the local code for future investigations.")} onClick={onUpdate}><ArrowDownToLine size={15} aria-hidden="true" />{t("Update")}</Button>}
  </div>;
}

export function EnvironmentLocalVersion({repository}:{repository:Environment["repositories"][number]}) {
  const {t,dateLocale}=useI18n();
  const [copied,setCopied]=useState(false);
  const [copyFailed,setCopyFailed]=useState(false);
  useEffect(()=>{setCopied(false);setCopyFailed(false);},[repository.sha]);
  useEffect(()=>{if(copied){const timer=setTimeout(()=>setCopied(false),2000);return()=>clearTimeout(timer);}},[copied]);
  function date(value?:string|null) {
    const parsed=value?new Date(value):null;
    return parsed&&!Number.isNaN(parsed.getTime())?parsed.toLocaleString(dateLocale):t("Verification date not recorded");
  }
  return <div className="min-w-0 text-sm">
    <span className="break-words">{repository.branch}</span>
    <details className="repository-version mt-1 text-xs muted">
      <summary className="flex w-fit cursor-pointer items-center gap-1">{t("Local version details")}<ChevronDown size={12} aria-hidden="true"/></summary>
      <dl className="mt-3 space-y-2">
        <div><dt>{t("Local commit")}</dt><dd className="mt-1 flex flex-wrap items-center gap-2">
          <code title={repository.sha}>{repository.sha.slice(0,10)||"—"}</code>
          {!!repository.sha&&<Button type="button" variant="ghost" size="sm" aria-label={t("Copy full local commit")} onClick={async()=>{
            try{await navigator.clipboard.writeText(repository.sha);setCopied(true);setCopyFailed(false);}catch{setCopyFailed(true);}
          }}>{copied?<Check size={13} aria-hidden="true"/>:<Clipboard size={13} aria-hidden="true"/>}{t(copied?"Copied":"Copy")}</Button>}
        </dd></div>
        <div><dt>{t("Last successful remote check")}</dt><dd>{date(repository.last_checked_at)}</dd></div>
        <div><dt>{t("Last local update")}</dt><dd>{repository.synced_at?date(repository.synced_at):t("Update date not recorded")}</dd></div>
      </dl>
      {copied&&<span role="status" className="sr-only">{t("Full local commit copied.")}</span>}
      {copyFailed&&<label className="mt-2 block">{t("Copy this full local commit manually")}<input readOnly className="mt-1 w-full rounded border bg-background p-2" value={repository.sha} onFocus={event=>event.target.select()}/></label>}
      <p className="mt-3 max-w-sm">{t(repository.sha?"This is the local code available for new investigations. Existing analyses keep their recorded commit.":"No local commit is available yet. Update this source before starting an investigation.")}</p>
    </details>
  </div>;
}
