"use client";
import { useEffect, useState } from "react";
import { api, send, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export type TicketConnector = {
  id: number;
  name: string;
  platform: string;
  base_url: string;
  username: string;
  api_version: string;
  has_secret: boolean;
  has_app_token: boolean;
  status: string;
  error: string;
  projects: string[];
  default_project: string;
};
export type Destination = { id: string; name: string };
const empty = {
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
  const { t } = useI18n();
  const [items, setItems] = useState<TicketConnector[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [form, setForm] = useState({ ...empty });
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const refresh = () =>
    api<TicketConnector[]>("/ticket-connectors").then(setItems);
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);
  function edit(item?: TicketConnector) {
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
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="lg:col-span-2">
      <h2>{t("Ticket publication connectors")}</h2>
      <p className="mt-2 text-sm muted">
        {t(
          "Publish only after explicit confirmation. Analysis assistants never receive these credentials.",
        )}
      </p>
      <div className="mt-5 flex flex-wrap gap-2">
        {items.map((item) => (
          <Button
            key={item.id}
            variant={selected === item.id ? "default" : "outline"}
            onClick={() => edit(item)}
          >
            {item.name} · {t(statuses[item.status] || item.status)}
          </Button>
        ))}
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
      <form
        className="mt-4"
        onSubmit={(event) => {
          event.preventDefault();
          action(async () => {
            const payload: Record<string, unknown> = {
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
            <label htmlFor="connector-name">{t("Connector name")}</label>
            <Input
              id="connector-name"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="connector-platform">{t("Platform")}</label>
            <select
              id="connector-platform"
              disabled={selected !== null}
              value={form.platform}
              onChange={(e) =>
                setForm({
                  ...empty,
                  name: form.name,
                  platform: e.target.value,
                  api_version: "v1",
                  base_url:
                    e.target.value === "github" ? "https://api.github.com" : "",
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
                <label htmlFor="connector-url">{t("Instance URL")}</label>
                <Input
                  type="url"
                  id="connector-url"
                  required
                  value={form.base_url}
                  onChange={(e) =>
                    setForm({ ...form, base_url: e.target.value })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="connector-username">
                  {t("Username / email")}
                </label>
                <Input
                  id="connector-username"
                  value={form.username}
                  onChange={(e) =>
                    setForm({ ...form, username: e.target.value })
                  }
                  autoComplete="off"
                />
              </div>
              <div className="field">
                <label htmlFor="connector-secret">
                  {t("Secret / API token")}
                </label>
                <Input
                  id="connector-secret"
                  type="password"
                  value={form.secret}
                  onChange={(e) => setForm({ ...form, secret: e.target.value })}
                  autoComplete="new-password"
                />
                <p className="mt-2 text-xs muted">
                  {t("Leave empty to keep the saved secret.")}
                </p>
              </div>
              {form.platform === "glpi" && (
                <>
                  <div className="field">
                    <label htmlFor="connector-app-token">
                      {t("Application token")}
                    </label>
                    <Input
                      type="password"
                      id="connector-app-token"
                      value={form.app_token}
                      onChange={(e) =>
                        setForm({ ...form, app_token: e.target.value })
                      }
                      autoComplete="new-password"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="connector-version">
                      {t("API compatibility")}
                    </label>
                    <select
                      id="connector-version"
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
        {form.platform === "github" && (
          <p className="mt-4 text-sm muted">
            {t(
              "Uses the shared GitHub connection. No additional token is required.",
            )}
          </p>
        )}
        <div className="mt-5 flex flex-wrap gap-2">
          <Button disabled={busy}>{t("Save connector")}</Button>
          {selected !== null && (
            <>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const tested = await send<TicketConnector>(
                      `/ticket-connectors/${selected}/test`,
                    );
                    setItems((values) =>
                      values.map((v) => (v.id === tested.id ? tested : v)),
                    );
                    if (tested.status !== "CONNECTED")
                      throw new Error(tested.error || "Connection failed.");
                    setNotice("Connection verified.");
                  })
                }
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
        {!!destinations.length && (
          <fieldset className="mt-5 rounded-lg border p-4">
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
            <label htmlFor="connector-default">{t("Default project")}</label>
            <select
              id="connector-default"
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
      </form>
    </Card>
  );
}
