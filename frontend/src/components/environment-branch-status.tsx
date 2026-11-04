"use client";

import { Check, CheckCircle2, CircleHelp, Clipboard, Download, LoaderCircle } from "lucide-react";
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
  return <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs muted" data-branch-update-row>
    <span className="flex min-w-0 items-center gap-1" title={environment.git_check_running?t("Checking branches…"):["UNKNOWN","UNAVAILABLE"].includes(state)?t("The remote state is unavailable or needs a new check."):undefined}>
      {state==="CURRENT"?<CheckCircle2 size={15} className="shrink-0 text-[var(--success)]" aria-hidden="true"/>:["UNKNOWN","UNAVAILABLE","MISSING"].includes(state)?<CircleHelp size={15} className="shrink-0 muted" aria-hidden="true"/>:null}
      {label}
    </span>
    {update && <><span aria-hidden="true">-</span><button type="button" className="inline-flex items-center gap-1 rounded px-1 text-primary underline focus-visible:outline-2 disabled:cursor-not-allowed disabled:opacity-50" disabled={disabled}
      aria-label={t("Update {repository} · {branch}", { repository: repository.path || repository.repository, branch: repository.branch })}
      title={t("Update the local code for future investigations.")} onClick={onUpdate}><Download size={12} aria-hidden="true" />{t("Update source")}</button></>}
  </div>;
}

export function EnvironmentLocalVersion({repository}:{repository:Environment["repositories"][number]}) {
  const {t}=useI18n();
  const [copied,setCopied]=useState(false);
  const [copyFailed,setCopyFailed]=useState(false);
  useEffect(()=>{setCopied(false);setCopyFailed(false);},[repository.sha]);
  useEffect(()=>{if(copied){const timer=setTimeout(()=>setCopied(false),2000);return()=>clearTimeout(timer);}},[copied]);
  return <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm" data-local-version-row>
    <span className="break-words">{repository.branch}</span>
    {!!repository.sha&&<><span className="muted" aria-hidden="true">-</span><div className="repository-version text-xs muted">
        <div className="flex flex-wrap items-center gap-2">
          <code title={repository.sha}>{repository.sha.slice(0,10)||"—"}</code>
          <Button type="button" variant="ghost" size="sm" aria-label={t("Copy full local commit")} onClick={async()=>{
            try{await navigator.clipboard.writeText(repository.sha);setCopied(true);setCopyFailed(false);}catch{setCopyFailed(true);}
          }}>{copied?<Check size={13} aria-hidden="true"/>:<Clipboard size={13} aria-hidden="true"/>}{t(copied?"Copied":"Copy")}</Button>
        </div>
      {copied&&<span role="status" className="sr-only">{t("Full local commit copied.")}</span>}
      {copyFailed&&<label className="mt-2 block">{t("Copy this full local commit manually")}<input readOnly className="mt-1 w-full rounded border bg-background p-2" value={repository.sha} onFocus={event=>event.target.select()}/></label>}
    </div></>}
  </div>;
}
