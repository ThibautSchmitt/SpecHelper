"use client";
import { useI18n } from "@/lib/i18n";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { GitBranch, Paintbrush, RefreshCw, Settings } from "lucide-react";
import { ThemeControl } from "@/components/theme-control";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  TicketConnectors,
  UnassignedTicketConnectors,
} from "@/components/ticket-connectors";
import { GitSources } from "@/components/git-sources";
import {
  RepositoryPicker,
  duplicateSources,
  sourcePayload,
  type SourceSelection,
} from "@/components/repository-picker";
import { type AIConnection } from "@/components/ai-connections";
import { AISettings } from "@/components/ai-settings";
import { EnvironmentLibrary } from "@/components/environment-library";
import {
  DatabaseConnections,
  type DatabaseConnection,
} from "@/components/database-connections";
import { EnvironmentActions } from "@/components/environment-actions";
import { EnvironmentContext } from "@/components/environment-context";
import { api, send, statuses, type Environment } from "@/lib/api";

type Connections = {
  github: { status: string; account: string };
  ais: AIConnection[];
  databases: DatabaseConnection[];
};
export default function Admin() {
  return (
    <Suspense fallback={null}>
      <AdminPanel />
    </Suspense>
  );
}
function AdminPanel() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const libraryDraft = searchParams.get("library_draft");
  const libraryKind = searchParams.get("library_kind");
  const [tab, setTab] = useState("general");
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
  const draftVersion = useRef(0);
  function updateSettings(changes: Partial<typeof settings>) {
    draftVersion.current += 1;
    setSettings((previous) => ({ ...previous, ...changes }));
  }
  const [selection, setSelection] = useState<SourceSelection[]>([
    { repository: "", branch: "" },
  ]);
  const [envName, setEnvName] = useState("");
  const [dbId, setDbId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    const version = ++refreshVersion.current;
    const draft = draftVersion.current;
    const [c, e, s] = await Promise.all([
      api<Connections>("/connections"),
      api<Environment[]>("/environments"),
      api<typeof settings>("/settings"),
    ]);
    if (version !== refreshVersion.current) return;
    setConnections(c);
    setEnvironments(e);
    if (draft === draftVersion.current) setSettings(s);
    setSettingsLoaded(true);
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    return () => {
      refreshVersion.current += 1;
    };
  }, []);
  useEffect(() => {
    if (libraryDraft) setTab("ai-agents");
  }, [libraryDraft]);
  useEffect(() => {
    const timer = setInterval(() => {
      api<Environment[]>("/environments")
        .then(setEnvironments)
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
  const tabs = [
    { id: "general", label: t("General"), icon: Paintbrush },
    { id: "ai-agents", label: t("AI & Agents"), icon: Settings },
    { id: "environments", label: t("Environments"), icon: GitBranch },
  ];
  return (
    <div className="space-y-6">
      <header className="page-heading">
        <div className="page-title">
          <span className="page-icon">
            <Settings size={20} />
          </span>
          <div>
            <h1>{t("Settings")}</h1>
            <p className="muted">
              {t("Connect your tools and prepare analysis environments.")}
            </p>
          </div>
        </div>
      </header>
      <nav
        className="flex flex-wrap gap-1 border-b pb-3"
        aria-label={t("Administration")}
      >
        {tabs.map((item) => (
          <Button
            key={item.id}
            variant={tab === item.id ? "default" : "ghost"}
            onClick={() => {
              setTab(item.id);
              setError("");
              setNotice("");
            }}
          >
            <item.icon size={16} aria-hidden="true" />
            {item.label}
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
      {tab === "ai-agents" && (
        <AISettings
          key={`${libraryKind}:${libraryDraft}`}
          onChanged={refresh}
        />
      )}
      {tab === "environments" && (
        <div className="space-y-6">
          <GitSources />
          <DatabaseConnections
            values={connections?.databases || []}
            onChanged={refresh}
          />
          <UnassignedTicketConnectors
            environments={environments}
            onAssigned={refresh}
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
                        <td className="py-2 pr-4">
                          {r.path || r.repository}
                          {r.connection_name && (
                            <small className="mt-1 block muted">
                              {r.connection_name}
                            </small>
                          )}
                          {r.is_fork && (
                            <small className="mt-1 block muted">
                              {t("Fork")}
                              {r.parent?.path
                                ? ` · ${t("Parent repository")}: ${r.parent.path}`
                                : ""}
                            </small>
                          )}
                        </td>
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
              <EnvironmentContext environmentId={e.id} />
              <EnvironmentLibrary environmentId={e.id} />
              <TicketConnectors environmentId={e.id} environmentName={e.name} />
            </Card>
          ))}
          <Card>
            <h2 className="flex items-center gap-2">
              <GitBranch size={20} /> {t("New environment")}
            </h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (duplicateSources(selection)) {
                  setError(
                    t(
                      "This connection, project and branch are already selected.",
                    ),
                  );
                  return;
                }
                action(async () => {
                  await send("/environments", {
                    name: envName,
                    database_id: dbId ? Number(dbId) : null,
                    repositories: selection.map(sourcePayload),
                  });
                  setEnvName("");
                  setSelection([{ repository: "", branch: "" }]);
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
              <RepositoryPicker
                prefix="new-source"
                values={selection}
                onChange={setSelection}
                disabled={busy}
              />
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
              <Button
                className="mt-5"
                disabled={busy || duplicateSources(selection)}
              >
                {t("Create environment")}
              </Button>
            </form>
          </Card>
        </div>
      )}
      {tab === "general" && (
        <Card className="max-w-2xl">
          <h2 className="flex items-center gap-2">
            <Paintbrush size={20} /> {t("Instance settings")}
          </h2>
          <div className="mt-5">
            <h3 className="mb-3">{t("Appearance")}</h3>
            <ThemeControl />
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const submitted = { ...settings };
              action(async () => {
                const current = await api<typeof settings>("/settings");
                await send(
                  "/settings",
                  {
                    ...current,
                    name: submitted.name,
                    short_label: submitted.short_label,
                    language: submitted.language,
                    primary_color: submitted.primary_color,
                  },
                  "PUT",
                );
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
                  onChange={(e) => updateSettings({ name: e.target.value })}
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
                    updateSettings({ short_label: e.target.value })
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
                  onChange={(e) => updateSettings({ language: e.target.value })}
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
                <div className="color-options">
                  {[
                    "#2563eb",
                    "#7c3aed",
                    "#0f766e",
                    "#d97706",
                    "#be123c",
                    "#475569",
                  ].map((color) => (
                    <button
                      key={color}
                      type="button"
                      style={{ background: color }}
                      aria-label={t("Choose primary color {color}", { color })}
                      aria-pressed={settings.primary_color === color}
                      onClick={() => updateSettings({ primary_color: color })}
                    />
                  ))}
                </div>
                <div className="flex items-center gap-4">
                  <input
                    id="instance-color"
                    type="color"
                    value={settings.primary_color}
                    onChange={(e) =>
                      updateSettings({ primary_color: e.target.value })
                    }
                    className="h-11 w-16 cursor-pointer rounded-md border p-1"
                  />
                  <span className="text-sm muted">
                    {settings.primary_color}
                  </span>
                </div>
              </div>
              <Button className="mt-6" disabled={busy}>
                {t("Save settings")}
              </Button>
            </fieldset>
          </form>
        </Card>
      )}
    </div>
  );
}
