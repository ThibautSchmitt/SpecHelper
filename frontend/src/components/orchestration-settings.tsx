"use client";
import { SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { publicRoles, roleLabels, type PublicRole } from "@/lib/orchestration";

export type OrchestrationSettings = {
  reliability_protocol?: string;
  global_instructions?: string;
  global_instruction_version?: number;
  global_instructions_requires_review?: boolean;
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
  useEffect(() => {
    let alive = true;
    const load = () => api<OrchestrationSettings>("/orchestration-settings")
      .then((data) => { if (alive) setValue(data); })
      .catch((e) => { if (alive) setError(e.message); });
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
    {value?.role_coverage && <section className="mt-4 rounded-lg border p-4" aria-label={t("Role coverage")}>
      <h3 className="text-sm font-medium">{t("Role coverage")} · {t(value.role_coverage.complete ? "Configuration complete" : "Configuration incomplete")}</h3>
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">{publicRoles.map(role => {
        const status = value.role_coverage!.roles[role];
        return <div key={role}><dt className="font-medium">{t(roleLabels[role])}</dt><dd className="mt-1">{t(!status.configured.length ? "Not covered" : !status.available.length ? "Covered · waiting for availability" : "Covered")}</dd></div>;
      })}</dl>
      <p className="mt-3 text-xs muted">{t("Missing role assignments block a new analysis. Busy assistants and exhausted quotas keep a configured analysis waiting; they do not invalidate its configuration.")}</p>
    </section>}
    <details className="mt-4 rounded-lg border p-4 text-sm">
      <summary className="cursor-pointer font-medium">{t("Instruction hierarchy")}</summary>
      <p className="mt-3 muted">{t("Backend security and mandatory roles take precedence over global instructions, then connection instructions. Skills provide optional procedures within these rules and never grant permissions.")}</p>
    </details>
    {value?.global_instructions_requires_review && <p role="alert" className="mt-4 text-sm text-amber-800 dark:text-amber-200">{t("Stored shared instructions match a configured credential. Review them in General settings.")}</p>}
    {error && <p role="alert" className="mt-4 text-sm text-red-700">{t(error)}</p>}
    {!value && !error && <p className="mt-4 text-sm muted">{t("Loading…")}</p>}
    {value && <form onSubmit={async (event) => {
      event.preventDefault();
      setBusy(true); setError(""); setNotice("");
      try {
        const { available_agents, available_skills, reliability_protocol, role_coverage, ...legacyBody } = value;
        const body = simplified ? { allow_same_family_fallback: value.allow_same_family_fallback, max_calls: value.max_calls } : legacyBody;
        void available_agents; void available_skills; void reliability_protocol; void role_coverage;
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
        <details className="rounded-lg border p-4">
          <summary className="cursor-pointer text-sm font-medium">{t("Advanced options")}</summary>
          <p className="mt-3 text-sm muted">{t("The call budget prevents loops. It is not a time limit. If it is reached before all checks finish, the result remains incomplete.")}</p>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <div className="field"><label htmlFor="orchestration-calls">{t("Maximum AI calls per analysis")}</label><Input id="orchestration-calls" type="number" min={["2.3", "2.4"].includes(value.reliability_protocol || "") ? 6 : 2} max={20} required value={value.max_calls} onChange={(e) => setValue({ ...value, max_calls: Number(e.target.value) })} /></div>
          {!simplified && <div className="field"><label htmlFor="orchestration-timeout">{t("Analysis time limit (seconds)")}</label><Input id="orchestration-timeout" type="number" min={30} max={285} required value={value.timeout_seconds} onChange={(e) => setValue({ ...value, timeout_seconds: Number(e.target.value) })} /></div>}
        </div>
        {simplified && <p className="text-sm muted">{t("Analyses have no fixed overall time limit. Tool safeguards and the call budget prevent stalled or repeated execution.")}</p>}
        </details>
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
