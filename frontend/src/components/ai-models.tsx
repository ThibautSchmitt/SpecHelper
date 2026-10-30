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
  useEffect(() => {
    const version = ++generation.current;
    setCatalog(null); setLoading(true); setError("");
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
      if (version === generation.current) {
        setCatalog(result);
        if (result.discovery.state !== "supported") setError(t(result.discovery.reason === "not_connected" ? "Provider connection required" : "Refresh failed; previous observations retained"));
      }
    } catch (failure) { if (version === generation.current) setError((failure as Error).message); }
    finally { setRefreshing(false); }
  }
  const options = (connectionId ? catalog?.items || [] : []).filter(item => item.agent === agent && item.enabled && ["SUPPORTED", "AVAILABLE"].includes(item.status));
  const selected = value ? options.find(item => item.identifier === value) : options.find(item => item.capabilities?.is_default);
  const efforts = selected?.capabilities?.reasoning_efforts || [];
  const nativeDefault = selected?.capabilities?.default_effort || "";
  const initialEffort = efforts.includes("medium") ? "medium" : efforts.includes(nativeDefault) ? nativeDefault : efforts[0] || "";
  useEffect(() => {
    if (agent !== "antigravity" && !effort && initialEffort && !loading && !refreshing) onEffortChange?.(initialEffort);
  }, [agent, effort, initialEffort, loading, refreshing, onEffortChange]);
  return <>
    <div className="field min-w-0"><label htmlFor="ai-config-model">{t("Model")}</label>
      <select id="ai-config-model" value={value} disabled={disabled || loading || refreshing} onChange={event => { onChange(event.target.value); onEffortChange?.(""); }}>
        <option value="">{t("Provider default model")}</option>
        {value && !options.some(item => item.identifier === value) && <option value={value}>{value}</option>}
        {options.map(item => <option key={item.id} value={item.identifier}>{item.name || item.identifier}</option>)}
      </select>
    </div>
    {agent !== "antigravity" && <div className="field min-w-0"><label htmlFor="ai-config-effort">{t("Reasoning")}</label>
      <select id="ai-config-effort" value={effort || initialEffort} disabled={disabled || loading || refreshing || !onEffortChange || !efforts.length} onChange={event => onEffortChange?.(event.target.value)}>
        {!efforts.length && !effort && <option value="">{t("Not reported")}</option>}
        {effort && !efforts.includes(effort) && <option value={effort} disabled>{effort} · {t("Unverified")}</option>}
        {efforts.map(level => <option key={level} value={level}>{level}</option>)}
      </select>
    </div>}
    <div className="col-span-full flex flex-wrap items-center gap-3 text-xs muted">
      <button type="button" className="inline-flex items-center gap-1 rounded border px-2 py-1" disabled={!connectionId || disabled || refreshing} aria-busy={refreshing} onClick={refresh}><RefreshCw size={13} aria-hidden="true" className={refreshing ? "animate-spin" : undefined} />{t("Refresh models")}</button>
      {(loading || refreshing) && <span role="status" className="sr-only">{t("Loading models…")}</span>}
    </div>
    {error && <p className="col-span-full text-sm" role="alert">{t(error)}</p>}
  </>;
}
