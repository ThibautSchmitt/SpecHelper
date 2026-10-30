"use client";
import { ProviderLogo } from "@/components/provider-logo";
import { Bot, Pencil, Plus, Power, RefreshCw, Trash2, Gauge, ExternalLink, ChevronDown, Download } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { OrchestrationSettings } from "@/components/orchestration-settings";
import { publicRoles, roleLabels, type PublicRole } from "@/lib/orchestration";
import { Card } from "@/components/ui/card";
import { ConnectButton } from "@/components/connect-button";
import { ModelSelect } from "@/components/ai-models";
import { api, send } from "@/lib/api";
import { assistantName, assistantProviders, type AssistantProvider } from "@/lib/assistant-providers";
import { observedQuota, remainingPercent, weeklyQuotaExhausted } from "@/lib/quota";
import type { CSSProperties } from "react";

function ConnectionQuotas({ connection, group }: { connection: AIConnection; group: AIConnection[] }) {
  const { t, dateLocale } = useI18n();
  const windows = new Map<string, QuotaWindow>();
  for (const value of group) for (const [name, window] of Object.entries(value.quota_windows || {})) {
    const old = windows.get(name);
    if (!old || (Date.parse(window.observed_at || "") || 0) > (Date.parse(old.observed_at || "") || 0)) windows.set(name, window);
  }
  const order = (name: string) => name === "session" ? 0 : name === "weekly" ? 1 : name === "daily" ? 2 : 3;
  const accountExhausted = observedQuota(connection).state === "Quota exhausted";
  const poolOrder = (name: string, window: QuotaWindow) => window.model_pool === "gemini" || name === "gemini-weekly" ? 0 : window.model_pool === "claude_gpt" || name === "3p-weekly" ? 1 : 2;
  const checked = group.map(value => value.quota_status?.checked_at).filter((value): value is string => !!value && Number.isFinite(Date.parse(value))).sort((a, b) => Date.parse(b) - Date.parse(a))[0];
  return <details className="connection-quotas mt-4">
    <summary className="flex cursor-pointer items-center gap-2 rounded py-2 text-sm"><Gauge size={16} aria-hidden="true" />{t("Quotas")}<ChevronDown className="quota-chevron" size={14} aria-hidden="true" /></summary>
    <dl className="connection-quota-preview" aria-label={t("All quota windows")}>
      {Array.from(windows).sort(([a, first], [b, second]) => poolOrder(a, first) - poolOrder(b, second) || order(a) - order(b)).map(([name, window]) => {
        const remaining = remainingPercent(window);
        const exhausted = window.exhausted || remaining === 0;
        const displayedRemaining = exhausted ? 0 : remaining;
        const reset = window.reset_at || window.resets_at;
        const observed = window.observed_at && Number.isFinite(Date.parse(window.observed_at)) ? window.observed_at : null;
        const stale = !observed || Date.now() - Date.parse(observed) > 300000 || (!!reset && Date.parse(reset) <= Date.now() && Date.parse(observed) < Date.parse(reset)) || group.some(value => ["error", "unavailable"].includes(value.quota_status?.state || ""));
        const label = name === "session" ? "Session quota" : name === "weekly" || window.window_type === "weekly" || ["gemini-weekly", "3p-weekly"].includes(name) ? "Weekly quota" : name === "daily" ? "Daily quota" : name === "credits" ? "Credits" : "Other quota window";
        const title = name === "session" && typeof window.window_minutes === "number" && Number.isFinite(window.window_minutes) && window.window_minutes > 0 ? window.window_minutes % 60 === 0 ? t("Quota {hours}h", { hours: window.window_minutes / 60 }) : t("Quota {minutes} min", { minutes: window.window_minutes }) : t(label);
        return <div key={name} data-quota-window={name} style={{ "--quota-ink": exhausted ? "var(--danger)" : remaining === null ? "var(--muted-foreground)" : remaining < 20 ? "var(--danger)" : remaining < 60 ? "var(--waiting)" : "var(--success)" } as CSSProperties}>
          <dt>{window.group_name && <span className="block">{t(window.group_name)}</span>}{title}</dt>
          <dd>{displayedRemaining !== null ? <><progress max={100} value={displayedRemaining} aria-label={t("Quota remaining")} /><span>{displayedRemaining === 0 ? t("0% remaining") : t("{percent}% remaining", { percent: Number(displayedRemaining.toFixed(1)) })}</span></> : typeof window.remaining_units === "number" && Number.isFinite(window.remaining_units) && window.remaining_units >= 0 ? `${window.remaining_units} ${window.unit || t("Credits")}` : t("Not reported")}</dd>
          {reset && Number.isFinite(Date.parse(reset)) && <dd className="text-xs muted">{t("Reset")}: {new Date(reset).toLocaleString(dateLocale)}</dd>}
          <dd className="text-xs muted">{t("Last observed")}: {observed ? new Date(observed).toLocaleString(dateLocale) : t("Not reported")}</dd>
          {stale && <dd className="text-xs muted">{t("Old data")}</dd>}
        </div>;
      })}
      {!windows.size && <div style={{ "--quota-ink": "var(--danger)" } as CSSProperties}><dt>{t("Quota")}</dt><dd>{accountExhausted ? <><progress max={100} value={0} aria-label={t("Quota remaining")} /><span>{t("0% remaining")}</span></> : t("Not reported")}</dd></div>}
    </dl>
    {group.some(value => value.quota_status?.state === "error") ? <p className="mt-2 text-xs text-red-700">{t("Quota refresh failed. Last known observations are preserved.")}</p> : group.some(value => value.quota_status?.state === "unavailable") ? <p className="mt-2 text-xs muted">{t(connection.agent === "claude" ? "This Claude Code version does not expose account quotas. Check your provider usage page." : "The provider did not return account quotas.")}</p> : null}
    {checked && <p className="mt-2 text-xs muted">{t("Last checked")}: {new Date(checked).toLocaleString(dateLocale)}</p>}
    {connection.agent === "claude" && <a className="mt-2 inline-flex items-center gap-1 text-xs text-primary underline" href="https://claude.ai/settings/usage" target="_blank" rel="noopener noreferrer">{t("Provider usage")}<ExternalLink size={12} aria-hidden="true" /></a>}
    {group.length > 1 && <p className="mt-2 text-xs muted">{t("These configurations share one authentication identity and the same quota.")}</p>}
  </details>;
}

export type QuotaWindow = {
  window_type?: string;
  source?: string;
  scope?: string;
  limit_id?: string;
  status?: string;
  model_pool?: string;
  group_name?: string;
  window_minutes?: number;
  remaining_units?: number;
  total_units?: number;
  unit?: string;
  remaining_percent?: number;
  used_percent?: number;
  reset_at?: string;
  resets_at?: string;
  exhausted?: boolean;
  observed_at?: string;
};
export type AIConnection = {
  id: number;
  name?: string;
  agent: AssistantProvider;
  model?: string;
  reasoning_effort?: string;
  status: string;
  availability: string;
  error?: string;
  enabled: boolean;
  account: string;
  checked_at?: string | null;
  identity_id?: string | number;
  quota_identity_id?: string | number;
  is_default?: boolean;
  preference?: number;
  quota_status?: { state: string; source?: string; checked_at?: string; reason?: string };
  quota_windows?: Record<string, QuotaWindow>;
  roles?: PublicRole[];
  additional_instructions?: string;
  skill_overrides?: Record<string, boolean>;
};
const emptyForm = {
  name: "",
  agent: "codex",
  model: "",
  reasoning_effort: "",
  enabled: true,
  preference: 100,
  share_identity_from: "",
  roles: [...publicRoles] as PublicRole[],
  additional_instructions: "",
  skill_overrides: {} as Record<string, boolean>,
};
type CLITool = {
  agent: AssistantProvider;
  installed_version: string;
  latest_version: string;
  update_available: boolean;
  update_status: string;
  update_error: string;
};
export function AIConnections({
  onChanged,
  simplified = false,
}: {
  values?: AIConnection[];
  simplified?: boolean;
  onChanged: () => Promise<void>;
}) {
  const { t } = useI18n();
  const [values, setValues] = useState<AIConnection[]>([]);
  const [showForm, setShowForm] = useState(false);
  const editor = useRef<HTMLFormElement>(null);
  const focusedConnection = useRef("");
  const [editing, setEditing] = useState<AIConnection | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cliTools, setCliTools] = useState<Partial<Record<AssistantProvider, CLITool>>>({});
  const [updatingCli, setUpdatingCli] = useState<AssistantProvider | null>(null);
  const previousCliVersions = useRef<Record<string, string>>({});
  const cliPending = Object.values(cliTools).some(tool => ["QUEUED", "RUNNING"].includes(tool.update_status));
  useEffect(() => {
    let alive = true;
    let reading = false;
    const read = async () => {
      if (reading) return;
      reading = true;
      try {
        const result = await api<{ items: CLITool[] }>("/cli-tools");
        if (alive && Array.isArray(result.items)) {
          const changed = result.items.some(tool => previousCliVersions.current[tool.agent] && previousCliVersions.current[tool.agent] !== tool.installed_version);
          previousCliVersions.current = Object.fromEntries(result.items.map(tool => [tool.agent, tool.installed_version]));
          setCliTools(Object.fromEntries(result.items.map(tool => [tool.agent, tool])));
          if (changed) window.dispatchEvent(new Event("models-updated"));
        }
      } catch {} finally { reading = false; }
    };
    void read();
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void read(); }, cliPending ? 2000 : 60000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [cliPending]);
  async function updateCli(agent: AssistantProvider) {
    setUpdatingCli(agent); setError("");
    try {
      const tool = await send<CLITool>(`/cli-tools/${agent}/update`);
      setCliTools(previous => ({ ...previous, [agent]: tool }));
    } catch (failure) { setError((failure as Error).message); }
    finally { setUpdatingCli(null); }
  }
  const [orchestration, setOrchestration] =
    useState<OrchestrationSettings | null>(null);
  const [removing, setRemoving] = useState<AIConnection | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  async function refresh() {
    setValues(await api<AIConnection[]>("/ai-connections"));
    window.dispatchEvent(new Event("connections-updated"));
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    let alive = true;
    const readQuotas = () => api<AIConnection[]>("/ai-connections")
      .then(result => { if (alive) setValues(result); }).catch(() => {});
    const quotaTimer = window.setInterval(() => { if (document.visibilityState === "visible") readQuotas(); }, 15000);
    window.addEventListener("quota-updated", readQuotas);
    const load = () =>
      api<OrchestrationSettings>("/orchestration-settings")
        .then((data) => {
          if (alive) setOrchestration(data);
        })
        .catch(() => {});
    load();
    window.addEventListener("orchestration-updated", load);
    return () => {
      alive = false;
      window.clearInterval(quotaTimer);
      window.removeEventListener("quota-updated", readQuotas);
      window.removeEventListener("orchestration-updated", load);
    };
  }, []);
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("connection");
    if (!id || focusedConnection.current === id || !values.some(value => String(value.id) === id)) return;
    const element = document.getElementById(`ai-connection-${id}`);
    element?.focus({ preventScroll: true }); element?.scrollIntoView({ block: "nearest" }); focusedConnection.current = id;
  }, [values]);
  useEffect(() => {
    if (removing) dialog.current?.showModal();
    else dialog.current?.close();
  }, [removing]);
  async function action(
    task: () => Promise<unknown>,
    message = "Connection settings saved.",
  ) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      await refresh();
      await onChanged();
      setNotice(t(message));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const identities = new Map<string, AIConnection[]>();
  for (const value of values) {
    const key = String(
      value.quota_identity_id ?? value.identity_id ?? `connection:${value.id}`,
    );
    identities.set(key, [...(identities.get(key) || []), value]);
  }
  useEffect(() => {
    if (showForm)
      editor.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, [showForm, editing]);
  const modelColumns = form.agent === "antigravity" ? (editing ? "md:grid-cols-1" : "md:grid-cols-2") : (editing ? "md:grid-cols-2" : "md:grid-cols-3");
  const connectionForm = showForm ? (
        <form
          aria-label={t(editing ? "Edit AI connection" : "New AI connection")}
          ref={editor}
          className="mt-6 border-t pt-5"
          onSubmit={(event) => {
            event.preventDefault();
            action(async () => {
              const { share_identity_from, skill_overrides, ...common } = form;
              const body = simplified ? common : { ...common, skill_overrides };
              await send(
                editing ? `/ai-connections/${editing.id}` : "/ai-connections",
                {
                  ...body,
                  reasoning_effort: form.agent === "antigravity" ? "" : form.reasoning_effort,
                  ...(!editing && share_identity_from
                    ? { share_identity_from: Number(share_identity_from) }
                    : {}),
                },
                editing ? "PUT" : "POST",
              );
              setEditing(null);
              setShowForm(false);
              setForm(emptyForm);
            });
          }}
        >
          <h3>{t(editing ? "Edit AI connection" : "New AI connection")}</h3>
          <div className="field">
            <label htmlFor="ai-config-name">{t("Connection name")}</label>
            <Input
              id="ai-config-name"
              required
              maxLength={100}
              value={form.name}
              onChange={(e) =>
                setForm((previous) => ({ ...previous, name: e.target.value }))
              }
            />
          </div>
          <div className={`grid min-w-0 gap-4 ${modelColumns}`} aria-label={t("Model configuration")}>
          {!editing && <div className="field">
            <label htmlFor="ai-config-provider">
              {t("Assistant")}
            </label>
            <select
              id="ai-config-provider"
              value={form.agent}
              onChange={(e) =>
                setForm({
                  ...form,
                  agent: e.target.value,
                  share_identity_from: "",
                  model: "", reasoning_effort: "",
                })
              }
            >
              {assistantProviders.map((provider) => (
                <option key={provider.id} value={provider.id}>{provider.name}</option>
              ))}
            </select>
          </div>}
            <ModelSelect agent={form.agent} connectionId={editing?.id || (form.share_identity_from ? Number(form.share_identity_from) : undefined)}
              value={form.model} effort={form.reasoning_effort}
              onChange={model => setForm(previous => ({ ...previous, model, reasoning_effort: "" }))}
              onEffortChange={reasoning_effort => setForm(previous => ({ ...previous, reasoning_effort }))} />
          </div>
          {!editing && (
            <div className="field">
              <label htmlFor="ai-config-identity">
                {t("Authentication identity")}
              </label>
              <select
                id="ai-config-identity"
                value={form.share_identity_from}
                onChange={(e) =>
                  setForm((previous) => ({
                    ...previous,
                    share_identity_from: e.target.value,
                    model: "", reasoning_effort: "",
                  }))
                }
              >
                <option value="">{t("New sign-in identity")}</option>
                {values
                  .filter((v) => v.agent === form.agent)
                  .map((v) => (
                    <option key={v.id} value={v.id}>
                      {t("Share with {name}", { name: v.name || v.agent })}
                    </option>
                  ))}
              </select>
            </div>
          )}
          <fieldset className="mt-5 space-y-3">
            <legend className="text-sm font-medium">
              {t("Analysis roles")}
            </legend>
            <p className="text-xs muted">
              {t(
                "These are the roles this assistant may perform. All three roles must be covered across enabled, connected assistants.",
              )}
            </p>
            {publicRoles.map((role) => (
              <label key={role} className="flex gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.roles.includes(role)}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      roles: e.target.checked
                        ? [...form.roles, role]
                        : form.roles.filter((item) => item !== role),
                    })
                  }
                />
                {t(roleLabels[role])}
              </label>
            ))}
          </fieldset>
          <details className="mt-5 rounded-lg border p-4">
            <summary className="cursor-pointer text-sm font-medium">
              {t(simplified ? "Specific instructions" : "Connection instructions and skills")}
            </summary>
            <div className="field">
              <label htmlFor="ai-config-instructions">
                {t(simplified ? "Specific instructions" : "Additional instructions")}
              </label>
              <Textarea
                id="ai-config-instructions"
                maxLength={12000}
                value={form.additional_instructions}
                onChange={(e) =>
                  setForm((previous) => ({
                    ...previous,
                    additional_instructions: e.target.value,
                  }))
                }
              />
            </div>
            {simplified ? <p className="mt-3 text-xs muted">{t("All active compatible skills are discoverable automatically. Each assistant loads only the skills useful for its current mission.")}</p> : <>
            <p className="mt-3 text-xs muted">
              {t(
                "Global instructions and skills are inherited. Only explicit skill overrides are stored for this connection.",
              )}
            </p>
            {orchestration ? (
              orchestration.available_skills.map((skill) => (
                <div className="field" key={skill.slug}>
                  <label htmlFor={`ai-skill-${skill.slug}`}>
                    {t(skill.name)}
                  </label>
                  <select
                    id={`ai-skill-${skill.slug}`}
                    value={
                      form.skill_overrides[skill.slug] === undefined
                        ? "inherit"
                        : form.skill_overrides[skill.slug]
                          ? "enabled"
                          : "disabled"
                    }
                    onChange={(e) => {
                      const overrides = { ...form.skill_overrides };
                      if (e.target.value === "inherit")
                        delete overrides[skill.slug];
                      else overrides[skill.slug] = e.target.value === "enabled";
                      setForm({ ...form, skill_overrides: overrides });
                    }}
                  >
                    <option value="inherit">
                      {t(
                        orchestration.default_skills.includes(skill.slug)
                          ? "Inherit (enabled globally)"
                          : "Inherit (disabled globally)",
                      )}
                    </option>
                    <option value="enabled">
                      {t("Enable for this connection")}
                    </option>
                    <option value="disabled">
                      {t("Disable for this connection")}
                    </option>
                  </select>
                </div>
              ))
            ) : (
              <p className="mt-3 text-xs muted">
                {t(
                  "Global skill settings are unavailable. Existing overrides will be preserved.",
                )}
              </p>
            )}
            </>}
            <p className="mt-3 text-xs muted">
              {t(
                "Instructions and skills cannot grant write access to analyzed repositories or databases.",
              )}
            </p>
          </details>
          {error && <p role="alert" className="mt-4 text-sm text-red-700">{t(error)}</p>}
          <div className="mt-4 flex gap-2">
            <Button disabled={busy}>
              {t(editing ? "Save connection" : "Add AI connection")}
            </Button>
            {showForm && (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setEditing(null);
                  setShowForm(false);
                  setForm(emptyForm);
                }}
              >
                {t("Cancel")}
              </Button>
            )}
          </div>
        </form>
  ) : null;
  return (
    <Card className="ai-connections min-w-0" aria-label={t("AI connections")}>
      <div className="section-heading">
        <h2><Bot size={18} aria-hidden="true" />{t("AI connections")}</h2>
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-label={t("New AI connection")}
          onClick={() => {
            setEditing(null);
            setForm(emptyForm);
            setShowForm(true);
          }}
        >
          <Plus size={15} aria-hidden="true" />{t("Add connection")}
        </Button>
      </div>
      <p className="mt-2 text-sm muted">
        {t(
          "Connect your assistants, choose models and configure their analysis roles.",
        )}
      </p>
      <div className="mt-5 space-y-4">
        {values.map((value) => (
          <section
            key={value.id}
            id={`ai-connection-${value.id}`}
            tabIndex={-1}
            aria-label={value.name || value.agent}
            className="ai-connection-card rounded-lg border p-4"
          >
            <div className="title-tags">
              <h3 className="flex items-center gap-2">
                <ProviderLogo provider={value.agent} />
                {value.name || assistantName(value.agent)}
              </h3>
              <div className="connection-tags">
                <span className="badge" data-state={value.enabled && value.status === "CONNECTED" ? "CONNECTED" : "DISABLED"}>{t(!value.enabled ? "Disabled" : value.status === "CONNECTED" ? "Connected" : "Not connected")}</span>
                <span className="badge connection-tag connection-model-tag" title={`${t("Model")}: ${value.model || t("Provider default model")}${value.agent !== "antigravity" && value.reasoning_effort ? ` · ${t("Reasoning effort")}: ${value.reasoning_effort}` : ""}`}>
                  {value.model || t("Provider default model")}{value.agent !== "antigravity" && value.reasoning_effort && ` ${value.reasoning_effort}`}
                </span>
                {publicRoles.filter(role => (value.roles ?? publicRoles).includes(role)).map(role => <span key={role} className="badge connection-tag connection-role-tag" data-role={role}>{t(roleLabels[role])}</span>)}
                {value.roles?.length === 0 && <span className="badge connection-tag">{t("No analysis role")}</span>}
              </div>
            </div>
            {value.account && ![value.name, assistantName(value.agent), "ChatGPT", "Codex", "Claude", "Antigravity"].some(name => name?.trim().toLowerCase() === value.account.trim().toLowerCase()) && <p className="connection-metadata mt-2 break-words text-sm muted">{value.account}</p>}
            {value.error && (
              <p className="mt-2 text-sm text-red-700">{t(value.error)}</p>
            )}
            {cliTools[value.agent] && <div className="connection-cli-version mt-3 flex flex-wrap items-center gap-2 text-xs muted">
              <span>{cliTools[value.agent]!.installed_version ? `v${cliTools[value.agent]!.installed_version}` : t("Version unknown")}</span>
              {["QUEUED", "RUNNING"].includes(cliTools[value.agent]!.update_status) ? <span role="status">{t(cliTools[value.agent]!.update_status === "QUEUED" ? "Update waiting for current tasks" : "Updating…")}</span> : cliTools[value.agent]!.update_available && <button type="button" className="inline-flex items-center gap-1 rounded px-1 text-primary underline focus-visible:outline-2" disabled={updatingCli !== null} title={t("Update to version {version}", { version: cliTools[value.agent]!.latest_version })} onClick={() => void updateCli(value.agent)}><Download size={12} aria-hidden="true" />{t("Update")}</button>}
              {cliTools[value.agent]!.update_error && <span role="alert" className="text-red-700">{t(cliTools[value.agent]!.update_error)}</span>}
            </div>}
            <ConnectionQuotas connection={value} group={identities.get(String(value.quota_identity_id ?? value.identity_id ?? `connection:${value.id}`)) || [value]} />
            {value.availability === "MODEL_UNAVAILABLE" && (
              <p className="mt-2 text-sm text-red-700">
                {t(
                  "The selected model is unavailable for this AI connection. Choose an accepted model in Settings and retry.",
                )}
              </p>
            )}
            <div className="connection-actions mt-3">
              {value.status !== "CONNECTED" && (              <ConnectButton
                provider={value.agent}
                startPath={`/ai-connections/${value.id}/auth/start`}
                identityLabel={value.name}
                reconnect={value.status === "AUTH_ERROR"} secondary={false}
                onConnected={() => {
                  action(async () => {}, "Connection successful.");
                }}
              />)}
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy}

                aria-label={t("Edit")}
                title={t("Edit")}
                aria-expanded={showForm && editing?.id === value.id}
                onClick={() => {
                  if (showForm && editing?.id === value.id) {
                    setEditing(null);
                    setShowForm(false);
                    setForm(emptyForm);
                    setError("");
                    return;
                  }
                  setShowForm(true);
                  setEditing(value);
                  setForm({
                    name: value.name || "",
                    agent: value.agent,
                    model: value.model || "",
                    reasoning_effort: value.reasoning_effort || "",
                    enabled: value.enabled,
                    preference: value.preference ?? 100,
                    share_identity_from: "",
                    roles: [...(value.roles ?? publicRoles)],
                    additional_instructions:
                      value.additional_instructions || "",
                    skill_overrides: { ...value.skill_overrides },
                  });
                }}
              >
                <Pencil size={16} aria-hidden="true" />{t("Edit")}
              </Button>
              <details className="action-menu" onKeyDown={event => { if (event.key === "Escape" && !(event.target instanceof Element && event.target.closest("dialog"))) { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
                <summary aria-label={t("More actions for {name}", { name: value.name || assistantName(value.agent) })}>⋯</summary>
                <div className="action-menu-items" onClick={event => { if (event.target instanceof Element && event.target.closest("button") && !event.target.closest("[data-connection-auth]")) { const menu = event.currentTarget.closest("details"); if (menu) { menu.open = false; menu.querySelector("summary")?.focus(); } } }}>
                  {value.status === "CONNECTED" && (              <ConnectButton
                provider={value.agent}
                label={t("Change account")}
                startPath={`/ai-connections/${value.id}/auth/start`}
                identityLabel={value.name}
                reconnect={value.status === "CONNECTED" || value.status === "AUTH_ERROR"}
                onConnected={() => {
                  action(async () => {}, "Connection successful.");
                }}
              />)}

              <Button
                type="button"
                size="sm"
                variant="outline"
                className="icon-action"
                aria-label={t("Refresh status and quotas")}
                title={t("Refresh status and quotas")}
                disabled={busy || value.availability === "BUSY"}
                onClick={() =>
                  action(
                    () => send(`/ai-connections/${value.id}/test`),
                    "Connection checked.",
                  )
                }
              >
                <RefreshCw size={16} aria-hidden="true" />{t("Refresh status and quotas")}
              </Button>

              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busy}
                className="icon-action"
                aria-label={t(value.enabled ? "Disable" : "Enable")}
                title={t(value.enabled ? "Disable" : "Enable")}
                onClick={() =>
                  action(() =>
                    send(
                      `/ai-connections/${value.id}`,
                      {
                        name: value.name,
                        agent: value.agent,
                        model: value.model || "",
                    reasoning_effort: value.reasoning_effort || "",
                        enabled: !value.enabled,
                        preference: value.preference ?? 100,
                        roles: value.roles ?? [...publicRoles],
                        additional_instructions:
                          value.additional_instructions || "",
                        ...(!simplified ? { skill_overrides: value.skill_overrides || {} } : {}),
                      },
                      "PUT",
                    ),
                  )
                }
              >
                <Power size={16} aria-hidden="true" />{t(value.enabled ? "Disable" : "Enable")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busy}
                className="icon-action"
                aria-label={t("Delete")}
                title={t("Delete")}
                onClick={() => setRemoving(value)}
              >
                <Trash2 size={16} aria-hidden="true" />{t("Delete")}
              </Button>

                </div>
              </details>
              {weeklyQuotaExhausted(value) && <span className="badge connection-quota-exhausted" data-state="ERROR">{t("Quota exhausted")}</span>}
            </div>
            {editing?.id === value.id && connectionForm}
          </section>
        ))}
      </div>
      {!editing && connectionForm}
      {error && !showForm && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {t(error)}
        </p>
      )}
      {notice && (
        <p role="status" className="mt-4 text-sm text-green-800">
          {notice}
        </p>
      )}
      <dialog
        ref={dialog}
        aria-label={t("Delete AI connection")}
        onCancel={(e) => {
          e.preventDefault();
          if (!busy) setRemoving(null);
        }}
        className="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-lg overflow-auto rounded-xl border bg-card p-6 text-foreground shadow-xl backdrop:bg-black/40"
      >
        <h2>{t("Delete AI connection")}</h2>
        <p className="mt-4 text-sm">
          {t(
            "Delete {name}? Existing requests and their audit history are preserved.",
            { name: removing?.name || "" },
          )}
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => setRemoving(null)}
          >
            {t("Cancel")}
          </Button>
          <Button
            disabled={busy}
            onClick={() => {
              if (removing)
                action(async () => {
                  await send(
                    `/ai-connections/${removing.id}`,
                    undefined,
                    "DELETE",
                  );
                  setRemoving(null);
                });
            }}
          >
            {t("Confirm deletion")}
          </Button>
        </div>
      </dialog>
    </Card>
  );
}
