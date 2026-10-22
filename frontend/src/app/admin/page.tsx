"use client";
import { useI18n } from "@/lib/i18n";
import { useEffect, useRef, useState } from "react";
import { GitBranch, Github, Paintbrush, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { TicketConnectors } from "@/components/ticket-connectors";
import { ConnectButton } from "@/components/connect-button";
import { AIConnections, type AIConnection } from "@/components/ai-connections";
import {
  DatabaseConnections,
  type DatabaseConnection,
} from "@/components/database-connections";
import { EnvironmentActions } from "@/components/environment-actions";
import { api, send, statuses, type Environment } from "@/lib/api";

type Connections = {
  github: { status: string; account: string };
  ais: AIConnection[];
  databases: DatabaseConnection[];
};
type Repo = { full_name: string; default_branch: string };
type System = {
  usage: string;
  runtime: string;
  max_analysis_seconds: number;
  jobs: {
    id: number;
    kind: string;
    status: string;
    error: string;
    started_at: string | null;
  }[];
};

export default function Admin() {
  const { t, dateLocale } = useI18n();
  const [tab, setTab] = useState("connections");
  const [connections, setConnections] = useState<Connections | null>(null);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [settings, setSettings] = useState({
    name: "SpecHelper",
    primary_color: "#2563eb",
    short_label: "",
    allow_confrontation: true,
    language: "fr",
  });
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const refreshVersion = useRef(0);
  const [system, setSystem] = useState<System | null>(null);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [orgs, setOrgs] = useState<{ login: string }[]>([]);
  const [organization, setOrganization] = useState("");
  const [repoPage, setRepoPage] = useState(1);
  const [repoMore, setRepoMore] = useState(false);
  const [selection, setSelection] = useState<
    {
      repository: string;
      branch: string;
      branches: string[];
      page: number;
      more: boolean;
    }[]
  >([{ repository: "", branch: "", branches: [], page: 1, more: false }]);
  const [envName, setEnvName] = useState("");
  const [dbId, setDbId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    const version = ++refreshVersion.current;
    const [c, e, s, y] = await Promise.all([
      api<Connections>("/connections"),
      api<Environment[]>("/environments"),
      api<typeof settings>("/settings"),
      api<System>("/system"),
    ]);
    if (version !== refreshVersion.current) return;
    setConnections(c);
    setEnvironments(e);
    setSettings(s);
    setSettingsLoaded(true);
    setSystem(y);
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    return () => {
      refreshVersion.current += 1;
    };
  }, []);
  useEffect(() => {
    const timer = setInterval(() => {
      api<Environment[]>("/environments")
        .then(setEnvironments)
        .catch(() => {});
      if (tab === "instance")
        api<System>("/system")
          .then(setSystem)
          .catch(() => {});
    }, 3000);
    return () => clearInterval(timer);
  }, [tab]);
  async function action(task: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      await refresh();
      setNotice(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadRepos(org = organization, page = 1) {
    const result = await api<Repo[]>(
      `/github/repositories?organization=${encodeURIComponent(org)}&page=${page}`,
    );
    setRepos((old) => (page === 1 ? result : [...old, ...result]));
    setRepoPage(page);
    setRepoMore(result.length === 100);
  }
  async function discover() {
    await loadRepos();
    const result = await api<{ login: string }[]>("/github/organizations");
    setOrgs(result);
  }
  async function selectRepo(index: number, repository: string) {
    const result = await api<{ name: string }[]>(
      `/github/branches?repository=${encodeURIComponent(repository)}`,
    );
    setSelection((old) =>
      old.map((r, i) =>
        i === index
          ? {
              repository,
              branch: result[0]?.name || "",
              branches: result.map((b) => b.name),
              page: 1,
              more: result.length === 100,
            }
          : r,
      ),
    );
  }
  async function moreVersions(index: number) {
    const current = selection[index];
    const result = await api<{ name: string }[]>(
      `/github/branches?repository=${encodeURIComponent(current.repository)}&page=${current.page + 1}`,
    );
    setSelection((old) =>
      old.map((r, i) =>
        i === index
          ? {
              ...r,
              branches: [...r.branches, ...result.map((b) => b.name)],
              page: r.page + 1,
              more: result.length === 100,
            }
          : r,
      ),
    );
  }
  const tabs = [
    { id: "connections", label: t("Connections") },
    { id: "environments", label: t("Environments") },
    { id: "instance", label: t("Instance") },
  ];
  return (
    <div className="space-y-6">
      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-primary">
          {t("Team settings")}
        </p>
        <h1>{t("Settings")}</h1>
        <p className="mt-2 muted">
          {t("Connect your tools and prepare analysis environments.")}
        </p>
      </div>
      <nav
        className="flex flex-wrap gap-1 border-b pb-3"
        aria-label={t("Administration")}
      >
        {tabs.map((t) => (
          <Button
            key={t.id}
            variant={tab === t.id ? "default" : "ghost"}
            onClick={() => {
              setTab(t.id);
              setError("");
              setNotice("");
            }}
          >
            {t.label}
          </Button>
        ))}
      </nav>
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"
        >
          {t(error)}
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="rounded-lg border border-green-200 bg-green-50 p-4 text-green-800"
        >
          {t(notice)}
        </div>
      )}
      {tab === "connections" && (
        <div className="grid items-start gap-6 lg:grid-cols-2">
          <Card>
            <div className="flex justify-between gap-4">
              <h2 className="flex items-center gap-2">
                <Github size={20} /> GitHub
              </h2>
              <span className="badge" data-state={connections?.github.status}>
                {t(statuses[connections?.github.status || "UNKNOWN"])}
              </span>
            </div>
            <p className="mt-3 text-sm muted">
              {connections?.github.account ||
                t("Connect your account to choose the projects to analyze.")}
            </p>
            <div className="mt-5 flex flex-wrap items-start gap-3">
              <ConnectButton
                provider="github"
                onConnected={() => {
                  refresh()
                    .then(() => setNotice(t("GitHub account connected.")))
                    .catch((e) => setError(e.message));
                }}
              />
              {connections?.github.status === "CONNECTED" && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    action(
                      () => send("/connections/github/test"),
                      t("GitHub connection verified."),
                    )
                  }
                >
                  {t("Test connection")}
                </Button>
              )}
            </div>
          </Card>
          <AIConnections values={connections?.ais || []} onChanged={refresh} />
          <TicketConnectors />
        </div>
      )}
      {tab === "environments" && (
        <div className="space-y-6">
          <DatabaseConnections
            values={connections?.databases || []}
            onChanged={refresh}
          />
          {environments.map((e) => (
            <Card key={e.id}>
              <div className="flex flex-wrap justify-between gap-3">
                <h2>{e.name}</h2>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="badge" data-state={e.status}>
                    {t(statuses[e.status] || e.status)}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy || ["PENDING", "SYNCING"].includes(e.status)}
                    onClick={() =>
                      action(
                        () => send(`/environments/${e.id}/sync`),
                        t("Synchronization scheduled."),
                      )
                    }
                  >
                    <RefreshCw size={14} />
                    {t("Synchronize")}
                  </Button>
                  <EnvironmentActions
                    value={e}
                    databases={connections?.databases || []}
                    disabled={busy || ["PENDING", "SYNCING"].includes(e.status)}
                    onChanged={async (message) => {
                      await refresh();
                      setNotice(message);
                    }}
                  />
                </div>
              </div>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="muted">
                    <tr>
                      <th className="pb-2 pr-4">{t("Project")}</th>
                      <th className="pb-2 pr-4">{t("Version")}</th>
                      <th className="pb-2">SHA</th>
                    </tr>
                  </thead>
                  <tbody>
                    {e.repositories.map((r) => (
                      <tr key={r.id}>
                        <td className="py-2 pr-4">{r.repository}</td>
                        <td className="pr-4">{r.branch}</td>
                        <td>
                          <code title={r.sha}>{r.sha.slice(0, 10) || "—"}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs muted">
                {t("Database:")} {e.database_name || t("None")}
              </p>
              {e.error && (
                <p className="mt-3 text-sm text-red-700">{t(e.error)}</p>
              )}
            </Card>
          ))}
          <Card>
            <h2 className="flex items-center gap-2">
              <GitBranch size={20} /> {t("New environment")}
            </h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                action(async () => {
                  await send("/environments", {
                    name: envName,
                    database_id: dbId ? Number(dbId) : null,
                    repositories: selection.map(({ repository, branch }) => ({
                      repository,
                      branch,
                    })),
                  });
                  setEnvName("");
                  setSelection([
                    {
                      repository: "",
                      branch: "",
                      branches: [],
                      page: 1,
                      more: false,
                    },
                  ]);
                }, t("Environment created. Synchronization in progress."));
              }}
            >
              <div className="field">
                <label htmlFor="env-name">{t("Name")}</label>
                <Input
                  id="env-name"
                  required
                  maxLength={100}
                  placeholder={t("Staging")}
                  value={envName}
                  onChange={(e) => setEnvName(e.target.value)}
                />
              </div>
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-sm">{t("Projects")}</h3>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => action(discover, t("Projects loaded."))}
                >
                  {t("Browse my GitHub projects")}
                </Button>
              </div>
              {orgs.length > 0 && (
                <div className="field">
                  <label htmlFor="organization">{t("Organization")}</label>
                  <select
                    id="organization"
                    value={organization}
                    onChange={(e) => {
                      setOrganization(e.target.value);
                      action(
                        () => loadRepos(e.target.value),
                        t("Projects loaded."),
                      );
                    }}
                  >
                    <option value="">{t("All accessible projects")}</option>
                    {orgs.map((o) => (
                      <option key={o.login}>{o.login}</option>
                    ))}
                  </select>
                </div>
              )}
              {selection.map((r, index) => (
                <div
                  key={index}
                  className="mt-4 grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]"
                >
                  <div>
                    <label htmlFor={`repo-${index}`}>
                      {t("Project")} {index + 1}
                    </label>
                    <select
                      id={`repo-${index}`}
                      required
                      value={r.repository}
                      onChange={(e) =>
                        action(
                          () => selectRepo(index, e.target.value),
                          t("Versions loaded."),
                        )
                      }
                    >
                      <option value="">{t("Choose a project")}</option>
                      {repos.map((repo) => (
                        <option key={repo.full_name}>{repo.full_name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor={`branch-${index}`}>
                      {t("Version")} {index + 1}
                    </label>
                    <select
                      id={`branch-${index}`}
                      required
                      value={r.branch}
                      onChange={(e) =>
                        setSelection((old) =>
                          old.map((item, i) =>
                            i === index
                              ? { ...item, branch: e.target.value }
                              : item,
                          ),
                        )
                      }
                    >
                      <option value="">{t("Choose a version")}</option>
                      {r.branches.map((b) => (
                        <option key={b}>{b}</option>
                      ))}
                    </select>
                    {r.more && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() =>
                          action(
                            () => moreVersions(index),
                            t("Versions loaded."),
                          )
                        }
                      >
                        {t("More versions")}
                      </Button>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={selection.length === 1}
                    aria-label={t("Remove project {number}", {
                      number: index + 1,
                    })}
                    onClick={() =>
                      setSelection((old) => old.filter((_, i) => i !== index))
                    }
                  >
                    {t("Remove")}
                  </Button>
                </div>
              ))}
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setSelection([
                      ...selection,
                      {
                        repository: "",
                        branch: "",
                        branches: [],
                        page: 1,
                        more: false,
                      },
                    ])
                  }
                >
                  {t("Add a project")}
                </Button>
                {repoMore && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      action(
                        () => loadRepos(organization, repoPage + 1),
                        t("Projects loaded."),
                      )
                    }
                  >
                    {t("More projects")}
                  </Button>
                )}
              </div>
              <div className="field">
                <label htmlFor="env-db">{t("Database")}</label>
                <select
                  id="env-db"
                  value={dbId}
                  onChange={(e) => setDbId(e.target.value)}
                >
                  <option value="">{t("None")}</option>
                  {connections?.databases.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
              <Button className="mt-5" disabled={busy}>
                {t("Create environment")}
              </Button>
            </form>
          </Card>
        </div>
      )}
      {tab === "instance" && (
        <Card className="max-w-2xl">
          <h2 className="flex items-center gap-2">
            <Paintbrush size={20} /> {t("Instance settings")}
          </h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              action(async () => {
                await send("/settings", settings, "PUT");
                window.dispatchEvent(new Event("settings-updated"));
              }, t("Instance settings saved."));
            }}
          >
            <fieldset disabled={!settingsLoaded || busy}>
              <div className="field">
                <label htmlFor="instance-name">{t("Instance name")}</label>
                <Input
                  id="instance-name"
                  required
                  maxLength={100}
                  value={settings.name}
                  onChange={(e) =>
                    setSettings({ ...settings, name: e.target.value })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="instance-label">
                  {t("Short label (optional)")}
                </label>
                <Input
                  id="instance-label"
                  maxLength={80}
                  value={settings.short_label || ""}
                  onChange={(e) =>
                    setSettings({ ...settings, short_label: e.target.value })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="instance-language">
                  {t("Application language")}
                </label>
                <select
                  id="instance-language"
                  value={settings.language || "fr"}
                  onChange={(e) =>
                    setSettings({ ...settings, language: e.target.value })
                  }
                >
                  <option value="en">{t("English")}</option>
                  <option value="fr">{t("French")}</option>
                </select>
                <p className="mt-2 text-sm muted">
                  {t(
                    "This sets the interface and the language of new analyses. Existing results are preserved.",
                  )}
                </p>
              </div>
              <div className="field">
                <label htmlFor="instance-color">{t("Primary color")}</label>
                <div className="flex items-center gap-4">
                  <input
                    id="instance-color"
                    type="color"
                    value={settings.primary_color}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        primary_color: e.target.value,
                      })
                    }
                    className="h-11 w-16 cursor-pointer rounded-md border p-1"
                  />
                  <span className="text-sm muted">
                    {settings.primary_color}
                  </span>
                </div>
              </div>
              <label className="mt-6 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.allow_confrontation !== false}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      allow_confrontation: e.target.checked,
                    })
                  }
                />
                {t("Allow comparison for new requests")}
              </label>
              <Button className="mt-6" disabled={busy}>
                {t("Save settings")}
              </Button>
            </fieldset>
          </form>
        </Card>
      )}
      {tab === "instance" && (
        <div className="space-y-6">
          <Card>
            <h2>{t("Request activity")}</h2>
            <div className="mt-4 space-y-3">
              {system?.jobs.length ? (
                system.jobs.map((j) => (
                  <div
                    key={j.id}
                    className="flex flex-wrap items-start justify-between gap-3 border-b pb-3"
                  >
                    <div>
                      <p className="text-sm font-medium">
                        #{j.id} ·{" "}
                        {j.kind === "sync" ? t("Synchronizing") : t("Analysis")}
                      </p>
                      <p className="mt-1 text-xs muted">
                        {j.started_at
                          ? new Date(j.started_at).toLocaleString(dateLocale)
                          : t("Queued")}
                      </p>
                      {j.error && (
                        <p className="mt-2 text-sm text-red-700">
                          {t(j.error)}
                        </p>
                      )}
                    </div>
                    <span className="badge">
                      {t(statuses[j.status] || j.status)}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-sm muted">{t("No jobs yet.")}</p>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
