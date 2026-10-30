"use client";

import { useRef, useState } from "react";
import { api, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

type Synchronization = {
  id: number;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string;
};

export function EnvironmentSyncHistory({ environmentId }: { environmentId: number }) {
  const { t, dateLocale } = useI18n();
  const [items, setItems] = useState<Synchronization[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  async function load() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      setItems(await api<Synchronization[]>(`/environments/${environmentId}/synchronization-history`));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  function timestamp(value: string | null) {
    const date = value ? new Date(value) : null;
    return date && !Number.isNaN(date.getTime())
      ? <time dateTime={value!}>{date.toLocaleString(dateLocale)}</time>
      : <span>{t("Unknown")}</span>;
  }
  return <details className="mt-4 min-w-0 rounded-lg border p-4" onToggle={event => {
    if (event.currentTarget.open && items === null && !pending.current) void load();
  }}>
    <summary className="cursor-pointer font-medium">{t("Synchronization history")}</summary>
    <div className="mt-3 space-y-3" aria-busy={busy}>
      <p className="text-xs muted">{t("Recent Git synchronization jobs for this environment. Successful jobs remain available here.")}</p>
      {busy && <p role="status" className="text-sm muted">{t("Loading synchronization history…")}</p>}
      {error && <div role="alert" className="space-y-2 text-sm text-red-700 dark:text-red-300"><p>{t(error)}</p><Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void load()}>{t("Retry")}</Button></div>}
      {items !== null && <>
        {!items.length && <p className="text-sm muted">{t("No synchronization jobs have been recorded for this environment.")}</p>}
        <ul className="space-y-3" aria-label={t("Recorded synchronizations")}>
          {items.map(item => <li key={item.id} className="min-w-0 space-y-2 rounded border p-3 text-sm">
            <div className="title-tags"><span className="font-medium">#{item.id}</span><span className="badge" data-state={item.status}>{t(item.status === "RUNNING" ? "In progress" : item.status === "QUEUED" ? "Waiting" : item.status === "ERROR" ? "Failed" : statuses[item.status] || item.status)}</span></div>
            <dl className="grid gap-2 text-xs sm:grid-cols-3">
              <div><dt className="muted">{t("Queued on")}</dt><dd className="mt-1 break-words">{timestamp(item.created_at)}</dd></div>
              <div><dt className="muted">{t("Started on")}</dt><dd className="mt-1 break-words">{timestamp(item.started_at)}</dd></div>
              <div><dt className="muted">{t("Finished on")}</dt><dd className="mt-1 break-words">{timestamp(item.finished_at)}</dd></div>
            </dl>
            {item.error && <p className="whitespace-pre-wrap break-words text-xs text-red-700 dark:text-red-300">{t(item.error)}</p>}
          </li>)}
        </ul>
        {!error && <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => void load()}>{t("Refresh history")}</Button>}
      </>}
    </div>
  </details>;
}
