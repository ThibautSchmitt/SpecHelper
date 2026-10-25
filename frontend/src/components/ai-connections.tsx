"use client";
import { ProviderLogo } from "@/components/provider-logo";
import { Bot, Pencil, Plus, Power, RefreshCw, Trash2, Gauge, ExternalLink } from "lucide-react";
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
import { api, send, statuses } from "@/lib/api";
import { assistantName, assistantProviders, type AssistantProvider } from "@/lib/assistant-providers";

export type QuotaWindow = {
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
  quota_windows?: { session?: QuotaWindow; weekly?: QuotaWindow };
  roles?: PublicRole[];
  additional_instructions?: string;
  skill_overrides?: Record<string, boolean>;
};
const emptyForm = {
  name: "",
  agent: "codex",
  model: "",
  enabled: true,
  is_default: false,
  preference: 100,
  share_identity_from: "",
  roles: [...publicRoles] as PublicRole[],
  additional_instructions: "",
  skill_overrides: {} as Record<string, boolean>,
};
export function AIConnections({
  onChanged,
  simplified = false,
}: {
  values?: AIConnection[];
  simplified?: boolean;
  onChanged: () => Promise<void>;
}) {
  const { t, dateLocale } = useI18n();
  const [values, setValues] = useState<AIConnection[]>([]);
  const [showForm, setShowForm] = useState(false);
  const editor = useRef<HTMLFormElement>(null);
  const [editing, setEditing] = useState<AIConnection | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
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
      window.removeEventListener("orchestration-updated", load);
    };
  }, []);
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
  function quota(window?: QuotaWindow) {
    if (!window) return t("Unknown");
    const percent =
      window.remaining_percent ??
      (window.used_percent !== undefined
        ? 100 - window.used_percent
        : undefined);
    const reset = window.reset_at || window.resets_at;
    return `${window.exhausted ? t("Quota exhausted") : percent === undefined ? t("Unknown") : t("{percent}% remaining", { percent: Math.max(0, Math.min(100, percent)) })}${reset && !Number.isNaN(Date.parse(reset)) ? ` · ${t("Reset")}: ${new Date(reset).toLocaleString(dateLocale)}` : ""}`;
  }
  useEffect(() => {
    if (showForm)
      editor.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, [showForm, editing]);
  return (
    <Card className="min-w-0" aria-label={t("AI connections")}>
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
            aria-label={value.name || value.agent}
            className="rounded-lg border p-4"
          >
            <div className="flex flex-wrap justify-between gap-2">
              <h3 className="flex items-center gap-2">
                <ProviderLogo provider={value.agent} />
                {value.name || assistantName(value.agent)}
                {value.is_default && (
                  <span className="ml-2 text-xs muted">{t("Default")}</span>
                )}
              </h3>
              <span className="badge" data-state={!value.enabled ? "DISABLED" : value.status !== "CONNECTED" ? value.status : value.availability}>
                {t(
                  !value.enabled
                    ? "Disabled"
                    : value.status !== "CONNECTED"
                      ? statuses[value.status] || value.status
                      : statuses[value.availability] || value.availability,
                )}
              </span>
            </div>
            <p className="mt-2 break-words text-sm muted">
              {assistantName(value.agent)} ·{" "}
              {value.account ||
                t(
                  value.status === "CONNECTED"
                    ? "Account not reported"
                    : "Not connected",
                )}{" "}
              · {value.model || t("Provider default model")}
            </p>
            {value.error && (
              <p className="mt-2 text-sm text-red-700">{t(value.error)}</p>
            )}
            <p className="mt-2 text-xs muted">
              {t("Roles")}:{" "}
              {(value.roles ?? publicRoles)
                .map((role) => t(roleLabels[role] || role))
                .join(" · ") || t("No analysis role")}
            </p>
            {value.availability === "MODEL_UNAVAILABLE" && (
              <p className="mt-2 text-sm text-red-700">
                {t(
                  "The selected model is unavailable for this AI connection. Choose an accepted model in Settings and retry.",
                )}
              </p>
            )}
            <div className="connection-actions mt-3">
              <ConnectButton
                provider={value.agent}
                startPath={`/ai-connections/${value.id}/auth/start`}
                identityLabel={value.name}
                onConnected={() => {
                  action(async () => {}, "Connection successful.");
                }}
              />
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
                <RefreshCw size={16} aria-hidden="true" />
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy}
                className="icon-action"
                aria-label={t("Edit")}
                title={t("Edit")}
                onClick={() => {
                  setShowForm(true);
                  setEditing(value);
                  setForm({
                    name: value.name || "",
                    agent: value.agent,
                    model: value.model || "",
                    enabled: value.enabled,
                    is_default: !!value.is_default,
                    preference: value.preference ?? 100,
                    share_identity_from: "",
                    roles: [...(value.roles ?? publicRoles)],
                    additional_instructions:
                      value.additional_instructions || "",
                    skill_overrides: { ...value.skill_overrides },
                  });
                }}
              >
                <Pencil size={16} aria-hidden="true" />
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
                        enabled: !value.enabled,
                        is_default: value.is_default,
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
                <Power size={16} aria-hidden="true" />
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busy}
                className="icon-action text-red-700"
                aria-label={t("Delete")}
                title={t("Delete")}
                onClick={() => setRemoving(value)}
              >
                <Trash2 size={16} aria-hidden="true" />
              </Button>
            </div>
          </section>
        ))}
      </div>
      <div className="account-quotas mt-5">
        <h3 className="flex items-center gap-2"><Gauge size={17} aria-hidden="true" />{t("Account quotas")}</h3>
        {Array.from(identities.entries()).map(([id, group]) => (
          <div key={id} className="rounded-lg bg-muted p-3 text-sm">
            <p className="font-medium break-words">
              {group[0].account || group[0].name} ·{" "}
              {group.map((v) => v.name).join(", ")}
            </p>
            <p className="mt-2">
              {t("Session quota")}:{" "}
              {quota(
                [...group]
                  .sort(
                    (a, b) =>
                      (Date.parse(b.checked_at || "") || 0) -
                      (Date.parse(a.checked_at || "") || 0),
                  )
                  .find((value) => value.quota_windows?.session)?.quota_windows
                  ?.session,
              )}
            </p>
            <p className="mt-1">
              {t("Weekly quota")}:{" "}
              {quota(
                [...group]
                  .sort(
                    (a, b) =>
                      (Date.parse(b.checked_at || "") || 0) -
                      (Date.parse(a.checked_at || "") || 0),
                  )
                  .find((value) => value.quota_windows?.weekly)?.quota_windows
                  ?.weekly,
              )}
            </p>
            <p className="mt-2 text-xs muted">
              {t("Last observed")}: {(() => {
                const timestamps = group.flatMap((value) => Object.values(value.quota_windows || {}).map((window) => window?.observed_at)).filter((value): value is string => !!value && !Number.isNaN(Date.parse(value)));
                const latest = timestamps.sort((a, b) => Date.parse(b) - Date.parse(a))[0];
                return latest ? new Date(latest).toLocaleString(dateLocale) : t("Unknown");
              })()}
            </p>
            {group.some((value) => value.quota_status?.state === "error") ? (
              <p className="mt-2 text-xs text-red-700">{t("Quota refresh failed. Last known observations are preserved.")}</p>
            ) : group.some((value) => value.quota_status?.state === "unavailable") ? (
              <p className="mt-2 text-xs muted">{t(group[0].agent === "claude" ? "This Claude Code version does not expose account quotas. Check your provider usage page." : "The provider did not return account quotas.")}</p>
            ) : null}
            {group.some((value) => value.quota_status?.checked_at) && <p className="mt-1 text-xs muted">{t("Last checked")}: {(() => {
              const checked = group.map((value) => value.quota_status?.checked_at).filter((value): value is string => !!value && !Number.isNaN(Date.parse(value))).sort((a,b) => Date.parse(b) - Date.parse(a))[0];
              return checked ? new Date(checked).toLocaleString(dateLocale) : t("Unknown");
            })()}</p>}
            {group[0].agent === "claude" && <a className="mt-2 inline-flex items-center gap-1 text-xs text-primary underline" href="https://claude.ai/settings/usage" target="_blank" rel="noopener noreferrer">{t("Provider usage")}<ExternalLink size={12} aria-hidden="true" /></a>}
            {group.length > 1 && (
              <p className="mt-2 text-xs muted">
                {t(
                  "These configurations share one authentication identity and the same quota.",
                )}
              </p>
            )}
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs muted">
        {t(
          "Quotas and reset times remain Unknown unless observed. API credentials are used only when explicitly configured.",
        )}
      </p>
      {showForm && (
        <form
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
          <div className="field">
            <label htmlFor="ai-config-provider">
              {t("Assistant provider")}
            </label>
            <select
              id="ai-config-provider"
              disabled={!!editing}
              value={form.agent}
              onChange={(e) =>
                setForm({
                  ...form,
                  agent: e.target.value,
                  share_identity_from: "",
                  model: "",
                })
              }
            >
              {assistantProviders.map((provider) => (
                <option key={provider.id} value={provider.id}>{provider.name}</option>
              ))}
            </select>
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
          <div className="field">
            <label htmlFor="ai-config-model">{t("Model")}</label>
            <ModelSelect
              agent={form.agent}
              connectionId={editing?.id || (form.share_identity_from ? Number(form.share_identity_from) : undefined)}
              value={form.model}
              onChange={(model) =>
                setForm((previous) => ({ ...previous, model }))
              }
            />
            <p className="mt-2 text-xs muted">
              {t(
                "Leave empty to use the provider default. Unsupported models produce an explicit runtime error.",
              )}
            </p>
          </div>
          <div className="field">
            <label htmlFor="ai-config-preference">
              {t("Availability preference")}
            </label>
            <Input
              id="ai-config-preference"
              type="number"
              min={0}
              max={2147483647}
              required
              value={form.preference}
              onChange={(e) =>
                setForm((previous) => ({
                  ...previous,
                  preference: Number(e.target.value),
                }))
              }
            />
            <p className="mt-2 text-xs muted">
              {t(
                "Lower values are preferred when automatic selection is used.",
              )}
            </p>
          </div>
          <fieldset className="mt-5 space-y-3">
            <legend className="text-sm font-medium">
              {t("Analysis roles")}
            </legend>
            <p className="text-xs muted">
              {t(
                "A connection can perform several roles, each in an independent session.",
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
          <label className="mt-4 flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) =>
                setForm((previous) => ({
                  ...previous,
                  is_default: e.target.checked,
                }))
              }
            />
            {t("Default connection when available")}
          </label>
          <label className="mt-3 flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) =>
                setForm((previous) => ({
                  ...previous,
                  enabled: e.target.checked,
                }))
              }
            />
            {t("Use this assistant for requests")}
          </label>
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
      )}
      {error && (
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
