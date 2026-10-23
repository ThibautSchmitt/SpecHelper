"use client";

import { useEffect, useRef, useState } from "react";
import { Pencil, RefreshCw } from "lucide-react";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { AIConnection } from "@/components/ai-connections";

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

export function ModelSelect({ agent, value, onChange, disabled = false, connectionId }: {
  agent: string; value: string; onChange: (value: string) => void; disabled?: boolean; connectionId?: number;
}) {
  const { t } = useI18n();
  const [items, setItems] = useState<AIModel[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  useEffect(() => {
    let alive = true;
    async function load() {
      const current = ++generation.current;
      setLoading(true);
      try {
        const catalog = await api<Catalog>(`/ai-models?agent=${encodeURIComponent(agent)}${connectionId ? `&connection_id=${connectionId}` : ""}`);
        if (alive && current === generation.current) { setItems(catalog.items); setError(""); }
      } catch (e) {
        if (alive && current === generation.current) setError((e as Error).message);
      } finally {
        if (alive && current === generation.current) setLoading(false);
      }
    }
    load();
    window.addEventListener("models-updated", load);
    return () => { alive = false; window.removeEventListener("models-updated", load); };
  }, [agent, connectionId]);
  const options = items.filter(item => item.enabled && item.status !== "UNAVAILABLE");
  const unavailable = items.find(item => item.identifier === value && (!item.enabled || item.status === "UNAVAILABLE"));
  return <>
    <select id="ai-config-model" value={value} disabled={disabled || loading} onChange={e => onChange(e.target.value)}>
      <option value="">{t("Provider default model")}</option>
      {value && !options.some(item => item.identifier === value) && <option value={value} disabled={!!unavailable}>{value} · {t(unavailable ? "Unavailable" : "Unverified")}</option>}
      {options.map(item => <option key={item.id} value={item.identifier}>{item.name || item.identifier} · {t(item.status === "SUPPORTED" ? "Supported" : item.status === "AVAILABLE" ? "Available" : "Unverified")}</option>)}
    </select>
    {loading && <p className="mt-2 text-xs muted" role="status">{t("Loading models…")}</p>}
    {error && <p className="mt-2 text-sm" role="alert">{t(error)}</p>}
    <p className="mt-2 text-xs muted">{t("Supported models do not guarantee access for every subscription.")}</p>
  </>;
}

export function AIModels() {
  const { t, dateLocale } = useI18n();
  const [connections, setConnections] = useState<AIConnection[]>([]);
  const [connectionId, setConnectionId] = useState("");
  const [agent, setAgent] = useState("codex");
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [form, setForm] = useState({ identifier: "", name: "", family: "" });
  const [editing, setEditing] = useState<AIModel | null>(null);
  const editor = useRef<HTMLFormElement>(null);
  useEffect(() => { if (editing) editor.current?.querySelector<HTMLInputElement>("#model-name")?.focus(); }, [editing]);
  const generation = useRef(0);
  async function load() {
    const current = ++generation.current;
    const result = await api<Catalog>(`/ai-models?agent=${agent}${connectionId ? `&connection_id=${connectionId}` : ""}`);
    if (current === generation.current) setCatalog(result);
  }
  useEffect(() => { api<AIConnection[]>("/ai-connections").then(setConnections).catch(e => setError(e.message)); }, []);
  useEffect(() => { setCatalog(null); load().catch(e => setError(e.message)); return () => { generation.current += 1; }; }, [agent, connectionId]);
  async function action(task: () => Promise<unknown>) {
    setBusy(true); setError(""); setNotice("");
    try { await task(); await load(); window.dispatchEvent(new Event("models-updated")); setNotice(t("Model catalog updated.")); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <Card>
    <h2>{t("Models")}</h2>
    <p className="mt-2 text-sm muted">{t("Refresh the provider catalog or add a documented model. Availability stays unknown until verified.")}</p>
    <fieldset disabled={busy}>
      <div className="field"><label htmlFor="model-provider">{t("Provider")}</label><select id="model-provider" value={agent} onChange={e => { setAgent(e.target.value); setConnectionId(""); setEditing(null); setForm({identifier:"",name:"",family:""}); }}><option value="codex">ChatGPT / Codex</option><option value="claude">Claude Code</option></select></div>
      <div className="field"><label htmlFor="model-connection">{t("AI connection")}</label><select id="model-connection" value={connectionId} onChange={e => setConnectionId(e.target.value)}><option value="">{t("Select a connection")}</option>{connections.filter(c => c.agent === agent).map(c => <option key={c.id} value={c.id}>{c.name || c.agent}</option>)}</select></div>
      <Button type="button" variant="outline" disabled={!connectionId || busy} onClick={() => action(() => send(`/ai-connections/${connectionId}/models/refresh`))}><RefreshCw size={15} aria-hidden="true" />{t("Refresh models")}</Button>
    </fieldset>
    {error && <p role="alert" className="mt-4 text-sm">{t(error)}</p>}
    {notice && <p role="status" className="mt-4 text-sm">{notice}</p>}
    {!catalog ? <p role="status" className="mt-4 muted">{t("Loading models…")}</p> : <>
      <p className="mt-4 text-sm muted">{t("Discovery")}: {t(discoveryLabels[catalog.discovery.state] || "Unknown")}{catalog.discovery.reason && ` · ${t(discoveryLabels[catalog.discovery.reason] || "Unknown")}`}</p>
      {!catalog.items.length && <p className="mt-4 muted">{t("No models in this catalog.")}</p>}
      <ul className="mt-4 space-y-3">{catalog.items.map(item => <li key={item.id} className="rounded-lg border p-3">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><strong>{item.name || item.identifier}</strong><p className="text-xs muted">{item.identifier} · {item.family || t("Unknown")} · {t(item.status === "SUPPORTED" ? "Supported" : item.status === "AVAILABLE" ? "Available" : item.status === "UNAVAILABLE" ? "Unavailable" : "Unverified")}</p>{item.checked_at && <p className="text-xs muted">{new Date(item.checked_at).toLocaleString(dateLocale)}</p>}</div>
        <div className="flex flex-wrap gap-2"><Button type="button" size="sm" variant="outline" disabled={busy} aria-label={t("Edit {name}",{name:item.name})} onClick={() => {setEditing(item);setForm({identifier:item.identifier,name:item.name,family:item.family});}}><Pencil size={14} aria-hidden="true" /></Button><Button type="button" size="sm" variant="outline" disabled={busy || !connectionId} onClick={() => action(() => send(`/ai-connections/${connectionId}/models/${item.id}/test`))}>{t("Check model")}</Button><Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => action(() => send(`/ai-models/${item.id}`, {enabled: !item.enabled}, "PUT"))}>{t(item.enabled ? "Disable" : "Enable")}</Button></div></div>
      </li>)}</ul>
    </>}
    <form ref={editor} className="mt-6 border-t pt-4" onSubmit={e => { e.preventDefault(); action(async () => { if(editing) await send(`/ai-models/${editing.id}`, {name:form.name,family:form.family}, "PUT"); else await send("/ai-models", {agent, ...form}); setEditing(null);setForm({identifier:"",name:"",family:""}); }); }}>
      <h3>{t(editing ? "Edit model" : "Add a documented model")}</h3>
      <fieldset disabled={busy}>
        <div className="field"><label htmlFor="model-identifier">{t("Model identifier")}</label><Input id="model-identifier" disabled={!!editing} required maxLength={100} value={form.identifier} onChange={e => setForm({...form,identifier:e.target.value})} /></div>
        <div className="field"><label htmlFor="model-name">{t("Name")}</label><Input id="model-name" required maxLength={100} value={form.name} onChange={e => setForm({...form,name:e.target.value})} /></div>
        <div className="field"><label htmlFor="model-family">{t("Model family")}</label><Input id="model-family" pattern="[a-zA-Z0-9._-]*" maxLength={100} value={form.family} onChange={e => setForm({...form,family:e.target.value})} /></div>
        <div className="mt-4 flex flex-wrap gap-2"><Button disabled={busy}>{t(editing ? "Save model" : "Add model")}</Button>{editing && <Button type="button" variant="outline" disabled={busy} onClick={() => {setEditing(null);setForm({identifier:"",name:"",family:""});}}>{t("Cancel")}</Button>}</div>
      </fieldset>
    </form>
    <p className="mt-4 text-xs muted">{t("Model checks read metadata and do not consume an analysis. Copilot remains experimental and unavailable for production.")}</p>
  </Card>;
}
