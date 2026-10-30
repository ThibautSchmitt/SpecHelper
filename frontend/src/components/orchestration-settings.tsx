"use client";
import { SlidersHorizontal, UserRound, ScanEye, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
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

export function OrchestrationSettingsForm() {
  const { t } = useI18n();
  const [value, setValue] = useState<OrchestrationSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [connections, setConnections] = useState<AIConnection[]>([]);
  const [connectionsError, setConnectionsError] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () => Promise.allSettled([
      api<OrchestrationSettings>("/orchestration-settings"),
      api<AIConnection[]>("/ai-connections"),
    ]).then(([settings, assistants]) => {
      if (!alive) return;
      if (settings.status === "fulfilled") setValue(settings.value);
      else setError(settings.reason.message);
      if (assistants.status === "fulfilled") setConnections(assistants.value);
      setConnectionsError(assistants.status === "rejected");
    });
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
  return <Card>
    <h2 className="flex items-center gap-2"><SlidersHorizontal size={18} />{t("Analysis configuration")}</h2>
    {value && <p className="mt-2 text-sm muted">{t(["2.3", "2.4"].includes(value.reliability_protocol || "") ? "Questions and requests use an Analyst, an independent Counter-analyst and a Verifier. Each role works in a separate session; no role can approve its own analysis." : "Compared requests use one analyst and one independent counter-analyst. An optional verifier consolidates the evidence.")}</p>}
    <p className="mt-2 text-sm muted">{t("AI verification does not replace human approval of the ticket and goal.md.")}</p>
    {value?.role_coverage && <section className="mt-5" aria-label={t("Role coverage")}>
      <h3 className="text-sm font-medium">{t("Role coverage")} · {t(value.role_coverage.complete ? "Configuration complete" : "Configuration incomplete")}</h3>
      {connectionsError && <p role="status" className="mt-3 text-sm muted">{t("AI connection details are unavailable. Role coverage is retained.")}</p>}
      <div className="orchestration-role-grid mt-4">{publicRoles.map(role => {
        const status = value.role_coverage!.roles[role];
        const Icon = role === "analyst" ? UserRound : role === "counter_analyst" ? ScanEye : ShieldCheck;
        return <article key={role} className="orchestration-role-card min-w-0 rounded-xl border p-5" data-role={role} aria-labelledby={`coverage-${role}`}>
          <header className="flex flex-wrap items-center justify-between gap-3">
            <h4 id={`coverage-${role}`} className="flex items-center gap-2 text-sm font-semibold"><Icon size={18} aria-hidden="true" />{t(roleLabels[role])}</h4>
            <span className="badge" data-state={status.configured.length ? "READY" : "ERROR"}>{t(status.configured.length ? "Covered" : "Not covered")}</span>
          </header>
          <p className="mt-4 text-xs muted">{t("AI connections covering this role")}</p>
          {status.configured.length ? <ul className="mt-3 space-y-3">{status.configured.map(id => {
            const connection = connections.find(item => item.id === id);
            const available = status.available.includes(id);
            return <li key={id} className="flex min-w-0 items-start gap-2" data-connection-id={id}>
              {connection && <ProviderLogo provider={connection.agent} />}
              <div className="min-w-0 flex-1">
                <p className="break-words text-sm font-medium">{connection ? connection.name || assistantName(connection.agent) : t("Connection #{id}", { id })}</p>
                {connection?.model && <p className="mt-1 break-words text-xs muted">{connection.model}</p>}
              </div>
              <span className="badge shrink-0" data-state={available ? "READY" : "QUEUED"}>{t(available ? "Available" : "Waiting")}</span>
            </li>;
          })}</ul> : <p className="mt-3 text-sm muted">{t("No AI connection covers this role.")}</p>}
        </article>;
      })}</div>
      <p className="mt-3 text-xs muted">{t("Missing role assignments block a new analysis. Busy assistants and exhausted quotas keep a configured analysis waiting; they do not invalidate its configuration.")}</p>
    </section>}
    {error && <p role="alert" className="mt-4 text-sm text-red-700">{t(error)}</p>}
    {!value && !error && <p className="mt-4 text-sm muted">{t("Loading…")}</p>}
    {value && <form onSubmit={async (event) => {
      event.preventDefault();
      setBusy(true); setError(""); setNotice("");
      try {
        const { available_agents, available_skills, reliability_protocol, role_coverage, max_calls, ...legacyBody } = value;
        const body = simplified ? { allow_same_family_fallback: value.allow_same_family_fallback } : legacyBody;
        void available_agents; void available_skills; void reliability_protocol; void role_coverage; void max_calls;
        setValue(await send<OrchestrationSettings>("/orchestration-settings", body, "PUT"));
        setNotice(t("Orchestration settings saved."));
        window.dispatchEvent(new Event("orchestration-updated"));
      } catch (e) { setError((e as Error).message); }
      finally { setBusy(false); }
    }}>
      <fieldset disabled={busy} className="mt-5 space-y-5">
        {["2.3", "2.4"].includes(value.reliability_protocol || "") ? <p className="text-sm font-medium">{t("Independent review is required")}</p> : <><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={value.allow_confrontation !== false} onChange={(e) => setValue({ ...value, allow_confrontation: e.target.checked })} />{t("Independent counter-analysis")}</label>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={value.verifier_enabled} onChange={(e) => setValue({ ...value, verifier_enabled: e.target.checked })} />
          {t("Verify compared analyses")}
        </label></>}
        <div>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={value.allow_same_family_fallback} onChange={(e) => setValue({ ...value, allow_same_family_fallback: e.target.checked })} />
            {t("Allow the same model family when no different family is available")}
          </label>
          <p className="mt-2 text-xs muted">{t("Different eligible model families are always preferred. When fallback is disabled, the request waits explicitly for an eligible family.")}</p>
        </div>
        <p className="text-xs muted">{t("Automatic safeguards stop stalled or repeated steps and preserve completed observations.")}</p>
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
        <Button>{t("Save analysis settings")}</Button>
      </fieldset>
    </form>}
    {notice && <p role="status" className="mt-4 text-sm text-green-800">{notice}</p>}
  </Card>;
}
