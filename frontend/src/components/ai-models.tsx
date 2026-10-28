"use client";

import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export type AIModel = {
  id: number;
  agent: string;
  identifier: string;
  name: string;
  family: string;
  source: string;
  status: string;
  checked_at: string | null;
  enabled: boolean;
  capabilities?: { reasoning_efforts?: string[]; default_effort?: string; is_default?: boolean };
};
type Catalog = { items: AIModel[]; discovery: { state: string; reason: string; checked_at?: string } };
const discoveryLabels: Record<string, string> = {
  unknown: "Unknown", supported: "Supported", unavailable: "Unavailable", error: "Error",
  not_verified: "Model access not verified", not_refreshed: "Catalog not refreshed",
  unsupported_cli: "Discovery is not exposed by this CLI version",
  not_connected: "Provider connection required",
  catalog_not_entitlement: "Listed model; subscription access not verified",
  refresh_failed: "Refresh failed; previous observations retained",
  not_in_latest_catalog: "Absent from the latest returned catalog",
  successful_analysis: "Access confirmed by a successful analysis",
  model_rejected: "Model rejected during analysis",
};

export function ModelSelect({ agent, value, onChange, disabled = false, connectionId, effort = "", onEffortChange }: {
  agent: string; value: string; onChange: (value: string) => void; disabled?: boolean; connectionId?: number;
  effort?: string; onEffortChange?: (value: string) => void;
}) {
  const { t } = useI18n();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const generation = useRef(0);
  const requested = useRef("");
  useEffect(() => {
    const version = ++generation.current;
    setCatalog(null); setLoading(true); setError(""); requested.current = "";
    const load = () => api<Catalog>(`/ai-models?agent=${encodeURIComponent(agent)}${connectionId ? `&connection_id=${connectionId}` : ""}`)
      .then(result => { if (version === generation.current) { setCatalog(result); setError(""); } })
      .catch(failure => { if (version === generation.current) setError(failure.message); })
      .finally(() => { if (version === generation.current) setLoading(false); });
    load(); window.addEventListener("models-updated", load);
    return () => { generation.current++; window.removeEventListener("models-updated", load); };
  }, [agent, connectionId]);
  async function refresh() {
    if (!connectionId || refreshing) return;
    const version = generation.current;
    setRefreshing(true); setError("");
    try {
      const result = await send<Catalog>(`/ai-connections/${connectionId}/models/refresh${value ? `?model=${encodeURIComponent(value)}` : ""}`);
      if (version === generation.current) setCatalog(result);
    } catch (failure) { if (version === generation.current) setError((failure as Error).message); }
    finally { setRefreshing(false); }
  }
  const options = (connectionId ? catalog?.items || [] : []).filter(item => item.agent === agent && item.enabled && ["SUPPORTED", "AVAILABLE"].includes(item.status));
  const selected = value ? options.find(item => item.identifier === value) : options.find(item => item.capabilities?.is_default);
  const efforts = selected?.capabilities?.reasoning_efforts || [];
  useEffect(() => {
    if (agent !== "antigravity" || !connectionId || !value || !selected || selected.capabilities?.reasoning_efforts || refreshing) return;
    const key = `${connectionId}:${value}`;
    if (requested.current === key) return;
    requested.current = key;
    refresh();
  }, [agent, connectionId, value, selected, refreshing]);
  const stale = !!catalog && (catalog.discovery.state === "error" || !catalog.discovery.checked_at || Date.now()-Date.parse(catalog.discovery.checked_at)>300000);
  return <>
    <div className="field min-w-0"><label htmlFor="ai-config-model">{t("Model")}</label>
      <select id="ai-config-model" value={value} disabled={disabled || loading || refreshing} onChange={event => { onChange(event.target.value); onEffortChange?.(""); }}>
        <option value="">{t("Provider default model")}</option>
        {value && !options.some(item => item.identifier === value) && <option value={value}>{value} · {t("Unverified")}</option>}
        {options.map(item => <option key={item.id} value={item.identifier}>{item.name || item.identifier} · {item.identifier} · {t(item.status === "AVAILABLE" ? "Access confirmed" : "Access unverified")}</option>)}
      </select>
    </div>
    <div className="field min-w-0"><label htmlFor="ai-config-effort">{t("Reasoning")}</label>
      <select id="ai-config-effort" value={effort} disabled={disabled || loading || refreshing || !onEffortChange} onChange={event => onEffortChange?.(event.target.value)}>
        <option value="">{t("Default")}</option>
        {effort && !efforts.includes(effort) && <option value={effort} disabled>{effort} · {t("Unverified")}</option>}
        {efforts.map(level => <option key={level} value={level}>{level}</option>)}
      </select>
    </div>
    <div className="md:col-span-3 flex flex-wrap items-center gap-3 text-xs muted">
      <button type="button" className="inline-flex items-center gap-1 rounded border px-2 py-1" disabled={!connectionId || disabled || refreshing} onClick={refresh}><RefreshCw size={13} aria-hidden="true" />{t("Refresh models")}</button>
      {loading || refreshing ? <span role="status">{t("Loading models…")}</span> : stale ? <span>{t("Previous catalog; refresh needed")}</span> : null}
      {catalog && <span>{t(discoveryLabels[catalog.discovery.reason] || "Supported models do not guarantee access for every subscription.")}</span>}
      {!efforts.length && <span>{t("No reasoning levels reported for this model")}</span>}
    </div>
    {error && <p className="md:col-span-3 text-sm" role="alert">{t(error)}</p>}
  </>;
}
