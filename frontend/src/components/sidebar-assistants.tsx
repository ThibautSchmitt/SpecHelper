"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Clock3, RefreshCw } from "lucide-react";
import { AssistantLogo } from "@/components/assistant-logo";
import type { AIConnection } from "@/components/ai-connections";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { observedQuota } from "@/lib/quota";
import { assistantName } from "@/lib/assistant-providers";
import "./sidebar-assistants.css";

export function SidebarAssistants() {
  const { t } = useI18n();
  const [connections, setConnections] = useState<AIConnection[] | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const current = useRef<AIConnection[]>([]);
  const pending = useRef(false);
  const refreshAction = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    let alive = true;
    let reading = false;
    let resetTimer: number | undefined;
    async function load() {
      if (reading) return;
      reading = true;
      try {
        const values = await api<AIConnection[]>("/ai-connections");
        if (alive) {
          current.current = values; setConnections(values); setUnavailable(false);
          const resets = values.flatMap(connection => Object.values(connection.quota_windows || {}).map(window => Date.parse(window.reset_at || window.resets_at || ""))).filter(time => Number.isFinite(time) && time > Date.now());
          if (resets.length) {
            window.clearTimeout(resetTimer);
            resetTimer = window.setTimeout(() => { resetTimer = undefined; if (alive && navigator.onLine) refresh(); }, Math.min(Math.min(...resets)-Date.now()+500, 2147483647));
          }
          // A poll at the reset boundary must not cancel the pending refresh.
        }
      } catch { if (alive) setUnavailable(true); }
      finally { reading = false; }
    }
    async function refresh() {
      if (pending.current) return;
      pending.current = true;
      if (alive) setRefreshing(true);
      const groups = new Set<string>();
      let failed = false;
      for (const connection of current.current) {
        const identity = String(connection.quota_identity_id || connection.identity_id || connection.id);
        if (!connection.enabled || connection.availability === "BUSY" || groups.has(identity)) continue;
        groups.add(identity);
        try { const result = await send<{ quota_refresh_state?: string }>(`/ai-connections/${connection.id}/quota/refresh`); if (result.quota_refresh_state === "error") failed = true; }
        catch { failed = true; }
      }
      await load();
      if (alive) window.dispatchEvent(new Event("quota-updated"));
      if (alive) { setRefreshing(false); if (failed) setUnavailable(true); }
      pending.current = false;
    }
    refreshAction.current = refresh;
    load();
    const readTimer = window.setInterval(() => { if (document.visibilityState === "visible") load(); }, 15000);
    const refreshTimer = window.setInterval(() => { if (document.visibilityState === "visible" && navigator.onLine) refresh(); }, 120000);
    window.addEventListener("connections-updated", load);
    return () => { alive = false; window.clearTimeout(resetTimer); window.clearInterval(readTimer); window.clearInterval(refreshTimer); window.removeEventListener("connections-updated", load); };
  }, []);
  return <div className="connection-indicators" aria-label={t("Connection status")}>
    <div className="flex items-center justify-between gap-2">
      <h2 className="connections-title">{t("Connected assistants")}</h2>
      <button type="button" className="rounded p-1 focus-visible:outline-2 focus-visible:outline-primary" aria-label={t("Refresh status and quotas")} title={t("Refresh status and quotas")} disabled={refreshing || !connections?.length} onClick={() => refreshAction.current()}>
        <RefreshCw size={14} aria-hidden="true" className={refreshing ? "animate-spin" : ""} />
      </button>
    </div>
    {connections?.map(connection => {
      const quota = observedQuota(connection);
      const windowName = quota.limiting === "session" ? "session" : quota.limiting === "weekly" || quota.limitingWindow?.window_type === "weekly" || ["gemini-weekly", "3p-weekly"].includes(quota.limiting) ? "weekly" : quota.limiting === "daily" ? "daily" : "remaining";
      const summary = quota.partiallyAvailable ? t("Partially available") : quota.state === "Quota remaining"
        ? t("{percent}% {window}", { percent: Number(quota.remaining!.toFixed(1)), window: t(windowName) }) : t(quota.state);
      const label = `${connection.name || assistantName(connection.agent)} · ${summary}`;
      return <section key={connection.id} className="sidebar-assistant" data-connection={connection.id} data-quota-state={quota.state} aria-label={connection.name || assistantName(connection.agent)}>
        <Link href={`/admin?tab=ai-agents&connection=${connection.id}`} className="sidebar-assistant-link" aria-label={label + ((quota.stale || unavailable) && quota.observed ? ` · ${t("Data needs refreshing")}` : "")} title={label}>
          <AssistantLogo agent={connection.agent} />
          <span className="connection-dot" data-quota-color={quota.color} data-stale={quota.stale || unavailable} data-connected={connection.enabled && connection.status === "CONNECTED" && ["AVAILABLE", "UNKNOWN"].includes(connection.availability || "UNKNOWN") && quota.state !== "Quota exhausted"} aria-hidden="true" />
          <span className="sidebar-assistant-label"><strong>{connection.name || assistantName(connection.agent)}</strong><small>{summary}</small></span>
          {(quota.stale || unavailable) && quota.observed && <Clock3 size={12} aria-label={t("Data needs refreshing")} className="shrink-0 muted" />}
        </Link>
      </section>;
    })}
    {!connections && <p>{t("AI connections")}: {t("Quota unknown")}</p>}
    {unavailable && <small role="status" className="block text-xs muted">{t("Refresh unavailable; previous observations retained")}</small>}
  </div>;
}
