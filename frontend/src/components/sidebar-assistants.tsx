"use client";

import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { AssistantLogo } from "@/components/assistant-logo";
import type { AIConnection } from "@/components/ai-connections";
import { api, send, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { observedQuota } from "@/lib/quota";
import "./sidebar-assistants.css";

export function SidebarAssistants() {
  const { t, dateLocale } = useI18n();
  const [connections, setConnections] = useState<AIConnection[] | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const current = useRef<AIConnection[]>([]);
  const pending = useRef(false);
  const refreshAction = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    let alive = true;
    let reading = false;
    async function load() {
      if (reading) return;
      reading = true;
      try {
        const values = await api<AIConnection[]>("/ai-connections");
        if (alive) { current.current = values; setConnections(values); setUnavailable(false); }
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
      if (alive) { setRefreshing(false); if (failed) setUnavailable(true); }
      pending.current = false;
    }
    refreshAction.current = refresh;
    load();
    const readTimer = window.setInterval(() => { if (document.visibilityState === "visible") load(); }, 15000);
    const refreshTimer = window.setInterval(() => { if (document.visibilityState === "visible" && navigator.onLine) refresh(); }, 120000);
    window.addEventListener("connections-updated", load);
    return () => { alive = false; window.clearInterval(readTimer); window.clearInterval(refreshTimer); window.removeEventListener("connections-updated", load); };
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
      const details = quota.windows.map(({ name, window, remaining }) => {
        const reset = window.reset_at || window.resets_at;
        return `${t(name === "weekly" ? "Weekly quota" : "Session quota")}: ${remaining === null ? t("Quota unknown") : t("{percent}% remaining", { percent: Number(remaining.toFixed(1)) })}${reset && Number.isFinite(Date.parse(reset)) ? ` · ${t("Reset")}: ${new Date(reset).toLocaleString(dateLocale)}` : ""}`;
      }).join("\n");
      return <section key={connection.id} className="sidebar-assistant" data-connection={connection.id} data-quota-state={quota.state} aria-label={connection.name || (connection.agent === "codex" ? "ChatGPT / Codex" : "Claude")}>
        <p><AssistantLogo agent={connection.agent} /><span className="min-w-0 break-words">{connection.name || (connection.agent === "codex" ? "ChatGPT / Codex" : "Claude")}<small>{t(connection.enabled ? statuses[connection.status === "CONNECTED" ? connection.availability : connection.status] || "Unknown" : "Disabled")}</small></span></p>
        <div title={details} className="sidebar-quota" data-quota-color={quota.color} data-stale={quota.stale || unavailable}>
          <span className="text-xs">{quota.state === "Quota remaining" ? t("{percent}% remaining", { percent: Number(quota.remaining!.toFixed(1)) }) : t(quota.state)}</span>
          {quota.remaining !== null && <div className="quota-track" role="meter" aria-label={t("Quota remaining")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={quota.remaining} aria-valuetext={t("{percent}% remaining", { percent: Number(quota.remaining.toFixed(1)) })}><span style={{ width: `${quota.remaining}%` }} /></div>}
          {quota.observed && <small className="block text-[10px] muted">{t("Observed: {time}", { time: new Date(quota.observed).toLocaleString(dateLocale) })}</small>}
          {(quota.stale || unavailable) && (quota.observed || quota.remaining !== null) && <small className="block text-[10px] muted">{t("Previous observation; refresh needed")}</small>}
        </div>
      </section>;
    })}
    {!connections && <p>{t("AI connections")}: {t("Quota unknown")}</p>}
    {unavailable && <small role="status" className="block text-xs muted">{t("Refresh unavailable; previous observations retained")}</small>}
  </div>;
}
