"use client";
import { ProviderLogo } from "@/components/provider-logo";
import { useEffect, useState } from "react";
import { api, send, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Ticket, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";

export type TicketConnector = {
  id: number;
  environment_id?: number | null;
  environment_ids: number[];
  enabled: boolean;
  name: string;
  platform: string;
  base_url: string;
  username: string;
  api_version: string;
  has_secret: boolean;
  has_app_token: boolean;
  status: string;
  checked_at?: string | null;
  error: string;
  projects: string[];
  default_project: string;
};
export type Destination = { id: string; name: string };
export const publicationPlatforms: Record<string, string> = { github: "GitHub", gitlab: "GitLab", jira: "Jira", glpi: "GLPI" };

const empty = {
  enabled: true,
  name: "",
  platform: "github",
  base_url: "https://api.github.com",
  username: "",
  secret: "",
  app_token: "",
  api_version: "v1",
  projects: [] as string[],
  default_project: "",
};

export function TicketConnectors() {
  const prefix = "publication-connection";
  const { t, dateLocale } = useI18n();
  const [items, setItems] = useState<TicketConnector[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [form, setForm] = useState({ ...empty });
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const refresh = () =>
    api<TicketConnector[]>("/ticket-connectors").then(setItems);
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);
  function edit(item?: TicketConnector) {
    setConfirmDelete(false);
    setShowForm(true);
    setSelected(item?.id ?? null);
    setDestinations([]);
    setError("");
    setNotice("");
    setForm(
      item ? { ...empty, ...item, secret: "", app_token: "" } : { ...empty },
    );
  }
  async function action(task: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      await refresh();
      window.dispatchEvent(new Event("publication-connections-updated"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function testConnection(id: number) {
    const tested = await send<TicketConnector>(`/ticket-connectors/${id}/test`);
    setItems(values => values.map(value => value.id === id ? tested : value));
    if (tested.status !== "CONNECTED") { setError("Connector check failed"); return; }
    setNotice("Connection verified.");
  }
  return (
    <div className="publication-connection-catalog" aria-label={t("Publication connections")}>
      <h2 className="flex items-center gap-2"><Ticket size={18} aria-hidden="true" />{t("Publication connections")}</h2>
      <p className="mt-2 text-sm muted">{t("Reusable publication accounts. Associate them with environments, then choose the account and destination when publishing.")}</p>
      <div className="mt-5 flex flex-wrap gap-2">
        {items.map((item) => <section key={item.id} className="min-w-0 w-full rounded-lg border p-3" aria-label={item.name}>
          <div className="title-tags"><h4 className="flex items-center gap-2 text-sm font-medium"><ProviderLogo provider={item.platform} />{item.name}</h4>
            <span className="badge">{publicationPlatforms[item.platform] || item.platform}</span>
            <span className="badge" data-state={!item.enabled ? "DISABLED" : item.status}>{t(!item.enabled ? "Disabled" : item.status === "UNKNOWN" ? item.checked_at ? "Connection needs verification" : "Not tested" : item.status === "UNAVAILABLE" ? "Verification unavailable" : item.status === "ERROR" ? "Failed" : statuses[item.status] || item.status)}</span></div>
          {item.checked_at && <p className="mt-1 text-xs muted">{t("Last checked")}: {new Date(item.checked_at).toLocaleString(dateLocale)}</p>}
          <div className="mt-3 flex flex-wrap gap-2"><Button type="button" size="sm" variant="outline" onClick={() => edit(item)} aria-label={t("Edit {name}", { name: item.name })}>{t("Edit")}</Button>
            <Button type="button" size="sm" variant="ghost" disabled={busy || item.enabled === false} onClick={() => action(() => testConnection(item.id))} aria-label={t("Test {name}", { name: item.name })}>{t("Test connection")}</Button>
            <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => action(() => {
              const {name, platform, base_url, username, api_version, projects, default_project} = item;
              return send(`/ticket-connectors/${item.id}`, {name, platform, base_url, username, api_version, projects, default_project, enabled: !item.enabled}, "PUT");
            })}>{t(item.enabled ? "Disable" : "Enable")}</Button></div>
          {item.error && <details className="mt-2 text-xs"><summary className="cursor-pointer">{t("Diagnostics")}</summary><p className="mt-2 whitespace-pre-wrap break-words">{item.error}</p></details>}
        </section>)}
        <Button variant="outline" onClick={() => edit()}>
          {t("New connector")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-4 text-red-700">
          {t(error)}
        </p>
      )}
      {notice && (
        <p role="status" className="mt-4 text-green-800">
          {t(notice)}
        </p>
      )}
      {showForm && <p className="mt-3 text-sm muted">{t("Browser sign-in for publication is not available yet. Use dedicated manual credentials.")}</p>}
      {showForm && (
        <form
          className="mt-4"
          onSubmit={(event) => {
            event.preventDefault();
            action(async () => {
              const payload: Record<string, unknown> = {
                enabled: form.enabled,
                name: form.name,
                platform: form.platform,
                base_url:
                  form.base_url ||
                  (form.platform === "github" ? "https://api.github.com" : ""),
                username: form.username,
                api_version: form.api_version || "v1",
                projects: form.projects,
                default_project: form.default_project,
                secret: form.secret,
                app_token: form.app_token,
              };
              if (!form.secret) delete payload.secret;
              if (!form.app_token) delete payload.app_token;
              const saved = await send<TicketConnector>(
                selected
                  ? `/ticket-connectors/${selected}`
                  : "/ticket-connectors",
                payload,
                selected ? "PUT" : "POST",
              );
              setSelected(saved.id);
              setForm({ ...empty, ...saved, secret: "", app_token: "" });
              setNotice("Connector saved.");
            });
          }}
        >
          <div className="grid gap-x-5 sm:grid-cols-2">
            <div className="field">
              <label htmlFor={`${prefix}-name`}>{t("Connection name")}</label>
              <Input
                id={`${prefix}-name`}
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor={`${prefix}-platform`}>{t("Platform")}</label>
              <select
                id={`${prefix}-platform`}
                disabled={selected !== null}
                value={form.platform}
                onChange={(e) =>
                  setForm({
                    ...empty,
                    name: form.name,
                    platform: e.target.value,
                    api_version: "v1",
                    base_url:
                      e.target.value === "github"
                        ? "https://api.github.com"
                        : "",
                  })
                }
              >
                {["github", "gitlab", "jira", "glpi"].map((v) => (
                  <option key={v} value={v}>
                    {
                      {
                        github: "GitHub Issues",
                        gitlab: "GitLab Issues",
                        jira: "Jira",
                        glpi: "GLPI",
                      }[v]
                    }
                  </option>
                ))}
              </select>
            </div>
            {form.platform !== "github" && (
              <>
                <div className="field">
                  <label htmlFor={`${prefix}-url`}>{t("Instance URL")}</label>
                  <Input
                    type="url"
                    id={`${prefix}-url`}
                    required
                    value={form.base_url}
                    onChange={(e) =>
                      setForm({ ...form, base_url: e.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label htmlFor={`${prefix}-username`}>
                    {t("Username / email")}
                  </label>
                  <Input
                    id={`${prefix}-username`}
                    value={form.username}
                    onChange={(e) =>
                      setForm({ ...form, username: e.target.value })
                    }
                    autoComplete="off"
                  />
                </div>
                <div className="field">
                  <label htmlFor={`${prefix}-secret`}>
                    {t("Secret / API token")}
                  </label>
                  <Input
                    id={`${prefix}-secret`}
                    type="password"
                    value={form.secret}
                    onChange={(e) =>
                      setForm({ ...form, secret: e.target.value })
                    }
                    autoComplete="new-password"
                  />
                  <p className="mt-2 text-xs muted">
                    {t("Leave empty to keep the saved secret.")}
                  </p>
                </div>
                {form.platform === "glpi" && (
                  <>
                    <div className="field">
                      <label htmlFor={`${prefix}-app-token`}>
                        {t("Application token")}
                      </label>
                      <Input
                        type="password"
                        id={`${prefix}-app-token`}
                        value={form.app_token}
                        onChange={(e) =>
                          setForm({ ...form, app_token: e.target.value })
                        }
                        autoComplete="new-password"
                      />
                    </div>
                    <div className="field">
                      <label htmlFor={`${prefix}-version`}>
                        {t("API compatibility")}
                      </label>
                      <select
                        id={`${prefix}-version`}
                        value={form.api_version}
                        onChange={(e) =>
                          setForm({ ...form, api_version: e.target.value })
                        }
                      >
                        <option value="v1">GLPI REST API v1 (legacy)</option>
                      </select>
                      <p className="mt-2 text-xs muted">
                        {t(
                          "Only GLPI REST API v1 is supported. API v2 is not compatible.",
                        )}
                      </p>
                    </div>
                  </>
                )}
              </>
            )}
          </div>
          {form.platform === "github" && <div className="field">
            <label htmlFor={`${prefix}-publication-secret`}>{t("Dedicated issue publication token")}</label>
            <Input id={`${prefix}-publication-secret`} type="password" autoComplete="new-password" required={selected === null} value={form.secret} onChange={(event) => setForm({ ...form, secret: event.target.value })} />
            <p className="mt-2 text-xs muted">{t("Use a separate fine-grained credential with issue permissions. Git source credentials cannot publish tickets.")}</p>
          </div>}
          <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={form.enabled} onChange={event => setForm({...form, enabled: event.target.checked})} />{t("Enabled")}</label>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button disabled={busy}>{t("Save connector")}</Button>
            {selected !== null && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                    onClick={() => action(() => testConnection(selected))}
                >
                  {t("Test connection")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    action(async () =>
                      setDestinations(
                        await api<Destination[]>(
                          `/ticket-connectors/${selected}/projects`,
                        ),
                      ),
                    )
                  }
                >
                  {t("Load accessible projects")}
                </Button>
              </>
            )}
          </div>
          {selected !== null && <div className="mt-3">
            <Button type="button" variant="ghost" className="icon-action text-red-700" disabled={busy} aria-label={t("Delete connector")} title={t("Delete connector")} onClick={() => setConfirmDelete(true)}><Trash2 size={16} aria-hidden="true" /></Button>
            {confirmDelete && <div role="alertdialog" aria-label={t("Delete connector")} className="mt-2 rounded-lg border p-4">
              <p className="text-sm">{t("Delete this connection? Associated environments and publication history prevent deletion.")}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button type="button" variant="outline" disabled={busy} onClick={() => setConfirmDelete(false)}>{t("Cancel")}</Button>
                <Button type="button" disabled={busy} onClick={() => action(async () => {
                  await send(`/ticket-connectors/${selected}`, undefined, "DELETE");
                  setSelected(null); setShowForm(false); setConfirmDelete(false); setNotice("Connector deleted.");
                })}>{t("Confirm deletion")}</Button>
              </div>
            </div>}
          </div>}
          {!!destinations.length && (
            <fieldset className="mt-5 rounded-lg border p-4"><p className="mb-3 text-xs muted">{t("Optional restrictions: leave all projects unchecked to allow any destination accessible to this account.")}</p>
              <legend className="px-2 text-sm font-semibold">
                {t("Allowed publication destinations")}
              </legend>
              {destinations.map((d) => (
                <label
                  key={d.id}
                  className="flex items-center gap-2 py-1 text-sm font-normal"
                >
                  <input
                    type="checkbox"
                    checked={form.projects.includes(d.id)}
                    onChange={(e) => {
                      const projects = e.target.checked
                        ? [...form.projects, d.id]
                        : form.projects.filter((p) => p !== d.id);
                      setForm({
                        ...form,
                        projects,
                        default_project: projects.includes(form.default_project)
                          ? form.default_project
                          : "",
                      });
                    }}
                  />
                  {d.name}
                </label>
              ))}
            </fieldset>
          )}
          {!!form.projects.length && (
            <div className="field">
              <label htmlFor={`${prefix}-default`}>{t("Default project")}</label>
              <select
                id={`${prefix}-default`}
                value={form.default_project}
                onChange={(e) =>
                  setForm({ ...form, default_project: e.target.value })
                }
              >
                <option value="">{t("None")}</option>
                {form.projects.map((id) => (
                  <option key={id} value={id}>
                    {destinations.find((d) => d.id === id)?.name || id}
                  </option>
                ))}
              </select>
              <p className="mt-2 text-xs muted">
                {t("Save the connector after changing allowed destinations.")}
              </p>
            </div>
          )}
          <Button
            type="button"
            variant="ghost"
            className="mt-4"
            onClick={() => {
              setShowForm(false);
              setSelected(null);
            }}
          >
            {t("Close")}
          </Button>
        </form>
      )}
    </div>
  );
}
