"use client";
import { SlidersHorizontal, UserRound, ScanEye, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { publicRoles, roleLabels, type PublicRole } from "@/lib/orchestration";
import { ProviderLogo } from "@/components/provider-logo";
import { assistantName } from "@/lib/assistant-providers";
import type { AIConnection } from "@/components/ai-connections";
import { ConnectionAvailability } from "@/components/connection-availability";
import { connectionAvailability } from "@/lib/quota";

export type OrchestrationSettings = {
  reliability_protocol?: string;
  global_instructions?: string;
  global_instruction_version?: number;
  global_instructions_requires_review?: boolean;
  preserved_guidance_review?: boolean;
  role_coverage?: { complete: boolean; roles: Record<PublicRole, { configured: number[]; available: number[] }> };
  migration_review?: { kind: "skill" | "instructions"; slug?: string; reason: string }[];
  tool_timeout_seconds?: number;
  allow_confrontation?: boolean;
  verifier_enabled: boolean;
  allow_same_family_fallback: boolean;
  max_calls: number;
  timeout_seconds: number;
  role_instructions: Record<PublicRole, string>;
  active_internal_agents: string[];
  default_skills: string[];
  available_agents: { slug: string; name: string; description?: string; required?: boolean }[];
  available_skills: { slug: string; name: string; description?: string }[];
};

function settingsBody(value: OrchestrationSettings) {
  if (value.reliability_protocol === "2.4") return { allow_same_family_fallback: value.allow_same_family_fallback };
  const { available_agents, available_skills, reliability_protocol, role_coverage, max_calls, ...body } = value;
  void available_agents; void available_skills; void reliability_protocol; void role_coverage; void max_calls;
  return body;
}

export function OrchestrationSettingsForm() {
  const { t } = useI18n();
  const [value, setValue] = useState<OrchestrationSettings | null>(null);
  const [saved, setSaved] = useState<OrchestrationSettings | null>(null);
  const dirty = !!value && !!saved && JSON.stringify(settingsBody(value)) !== JSON.stringify(settingsBody(saved));
  const editing = useRef(false);
  editing.current = dirty;
  const loadId = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [connections, setConnections] = useState<AIConnection[]>([]);
  const [connectionsError, setConnectionsError] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () => {
      const id = ++loadId.current;
      return Promise.allSettled([
        api<OrchestrationSettings>("/orchestration-settings"),
        api<AIConnection[]>("/ai-connections"),
      ]).then(([settings, assistants]) => {
        if (!alive || id !== loadId.current) return;
        if (settings.status === "fulfilled") {
          setSaved(settings.value);
          setValue(previous => previous && editing.current ? { ...previous, role_coverage: settings.value.role_coverage } : settings.value);
        }
        else setError(settings.reason.message);
        if (assistants.status === "fulfilled") setConnections(assistants.value);
        setConnectionsError(assistants.status === "rejected");
      });
    };
    load();
    window.addEventListener("connections-updated", load);
    window.addEventListener("quota-updated", load);
    return () => { alive = false; window.removeEventListener("connections-updated", load); window.removeEventListener("quota-updated", load); };
  }, []);
  function toggle(key: "default_skills" | "active_internal_agents", slug: string) {
    if (!value) return;
    setValue({ ...value, [key]: value[key].includes(slug)
      ? value[key].filter((item) => item !== slug) : [...value[key], slug] });
  }
  const simplified = value?.reliability_protocol === "2.4";
  return <section className="min-w-0" aria-label={t("Orchestration")}>
    <div className="section-heading"><h2><SlidersHorizontal size={18} aria-hidden="true" />{t("Orchestration")}</h2></div>
    <p className="mt-2 text-sm muted">{t("Deep analyses use three distinct roles with independent sessions.")}</p>
    <Card className="mt-5 min-w-0">
    {value?.role_coverage && <section aria-label={t("Role coverage")}>
      <h3 className="text-sm font-medium">{t("Role coverage")} · {t(value.role_coverage.complete ? "Configuration complete" : "Configuration incomplete")}</h3>
      {connectionsError && <p role="status" className="mt-3 text-sm muted">{t("AI connection details are unavailable. Role coverage is retained.")}</p>}
      <div className="orchestration-role-grid mt-4">{publicRoles.map(role => {
        const status = value.role_coverage!.roles[role];
        const availability = status.configured.map(id => connections.find(item => item.id === id)).map(connection => connection && !connectionsError ? connectionAvailability(connection).key : "unknown");
        const count = status.available.filter(id => availability[status.configured.indexOf(id)] === "available").length;
        const capacity = availability.includes("unknown") ? "Availability not confirmed" : "No connection available now";
        const Icon = role === "analyst" ? UserRound : role === "counter_analyst" ? ScanEye : ShieldCheck;
        return <article key={role} className="orchestration-role-card min-w-0 rounded-xl border p-4" data-role={role} aria-labelledby={`coverage-${role}`}>
          <header className="title-tags">
            <h4 id={`coverage-${role}`} className="flex items-center gap-2 text-sm font-semibold"><Icon size={18} aria-hidden="true" />{t(roleLabels[role])}</h4>
            <span className="badge" data-state={status.configured.length ? "READY" : "ERROR"}>{t(status.configured.length ? "Covered" : "Not covered")}</span>
          </header>
          {!!status.configured.length && count === 0 && <p className="mt-3 text-xs muted">{t(capacity)}</p>}
          {status.configured.length ? <ul className="mt-3 space-y-3">{status.configured.map(id => {
            const connection = connections.find(item => item.id === id);
            return <li key={id} className="flex min-w-0 items-start gap-2" data-connection-id={id}>
              {connection && <ProviderLogo provider={connection.agent} />}
              <div className="min-w-0 flex-1">
                <div className="title-tags"><p className="break-words text-sm font-medium">{connection ? connection.name || assistantName(connection.agent) : t("Connection #{id}", { id })}</p>
                  {connection && !connectionsError ? <ConnectionAvailability connection={connection} /> : <span className="badge ai-availability" data-availability="unknown">{t("Availability unknown")}</span>}
                </div>
                {connection?.model && <p className="mt-1 break-words text-xs muted">{connection.model}</p>}
              </div>
            </li>;
          })}</ul> : <p className="mt-3 text-sm muted">{t("No AI connection covers this role.")}</p>}
        </article>;
      })}</div>
    </section>}
    {error && <p role="alert" className="mt-4 text-sm text-red-700">{t(error)}</p>}
    {!value && !error && <p className="mt-4 text-sm muted">{t("Loading…")}</p>}
    {value && <form onSubmit={async (event) => {
      event.preventDefault();
      if (!dirty || busy) return;
      setBusy(true); setError(""); setNotice("");
      try {
        const updated = await send<OrchestrationSettings>("/orchestration-settings", settingsBody(value), "PUT");
        loadId.current++;
        setValue(updated); setSaved(updated);
        setNotice(t("Orchestration settings saved."));
        window.dispatchEvent(new Event("orchestration-updated"));
      } catch (e) { setError((e as Error).message); }
      finally { setBusy(false); }
    }}>
      <fieldset disabled={busy} className="mt-5 space-y-5">
        {!["2.3", "2.4"].includes(value.reliability_protocol || "") && <><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={value.allow_confrontation !== false} onChange={(e) => setValue({ ...value, allow_confrontation: e.target.checked })} />{t("Independent counter-analysis")}</label>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={value.verifier_enabled} onChange={(e) => setValue({ ...value, verifier_enabled: e.target.checked })} />
          {t("Verify compared analyses")}
        </label></>}
        <div>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={value.allow_same_family_fallback} onChange={(e) => { setValue({ ...value, allow_same_family_fallback: e.target.checked }); setNotice(""); }} />
            {t("Allow limited AI diversity")}
          </label>
          <p className="mt-2 text-xs muted">{t("If different model families are not available, SpecHelper can use the same family in independent sessions. This limitation will be reported in the results.")}</p>
        </div>
        {!simplified && <details className="rounded-lg border p-4">
          <summary className="cursor-pointer text-sm font-medium">{t("Advanced options")}</summary>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          {!simplified && <div className="field"><label htmlFor="orchestration-timeout">{t("Analysis time limit (seconds)")}</label><Input id="orchestration-timeout" type="number" min={30} max={285} required value={value.timeout_seconds} onChange={(e) => setValue({ ...value, timeout_seconds: Number(e.target.value) })} /></div>}
        </div>
        </details>}
        {!simplified && <details className="rounded-lg border p-4">
          <summary className="cursor-pointer font-medium text-sm">{t("Advanced role instructions and tools")}</summary>
          <p className="mt-3 text-xs muted">{t("Instructions and skills cannot grant write access to analyzed repositories or databases.")}</p>
          {publicRoles.map((role) => <div key={role} className="field"><label htmlFor={`role-instructions-${role}`}>{t("{role} instructions", { role: t(roleLabels[role]) })}</label><Textarea id={`role-instructions-${role}`} maxLength={12000} value={value.role_instructions[role] || ""} onChange={(e) => setValue({ ...value, role_instructions: { ...value.role_instructions, [role]: e.target.value } })} /></div>)}
          <fieldset className="mt-5 space-y-3"><legend className="font-medium text-sm">{t("Analysis tools")}</legend><p className="text-xs muted">{t("Required tools remain active to produce a complete analysis and its documents.")}</p>{value.available_agents.map((agent) => <label key={agent.slug} className="flex items-start gap-2 text-sm"><input type="checkbox" disabled={agent.required} checked={value.active_internal_agents.includes(agent.slug)} onChange={() => toggle("active_internal_agents", agent.slug)} /><span>{t(agent.name)}{agent.required && ` · ${t("Required")}`}{agent.description && <span className="mt-1 block text-xs muted">{t(agent.description)}</span>}</span></label>)}</fieldset>
          <fieldset className="mt-5 space-y-3"><legend className="font-medium text-sm">{t("Default skills")}</legend>{value.available_skills.map((skill) => <label key={skill.slug} className="flex items-start gap-2 text-sm"><input type="checkbox" checked={value.default_skills.includes(skill.slug)} onChange={() => toggle("default_skills", skill.slug)} /><span>{t(skill.name)}{skill.description && <span className="mt-1 block text-xs muted">{t(skill.description)}</span>}</span></label>)}</fieldset>
        </details>}
        <div className="mt-4 flex flex-wrap justify-end gap-2" data-editor-actions>
          <Button disabled={!dirty || busy}>{t("Save")}</Button>
        </div>
      </fieldset>
    </form>}
    {notice && <p role="status" className="mt-4 text-sm text-green-800">{notice}</p>}
    </Card>
  </section>;
}
