"use client";
import { useI18n } from "@/lib/i18n";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { GitBranch, Plug, Paintbrush, RefreshCw, Settings, Database, Plus } from "lucide-react";
import { ThemeControl } from "@/components/theme-control";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { TicketConnectors } from "@/components/ticket-connectors";
import { PublicationConnectionPicker, PublicationConnectionsSummary } from "@/components/publication-connections";
import { GitSources } from "@/components/git-sources";
import {
  RepositoryPicker,
  duplicateSources,
  sourcePayload,
  type SourceSelection,
} from "@/components/repository-picker";
import { type AIConnection } from "@/components/ai-connections";
import { AISettings } from "@/components/ai-settings";
import type { OrchestrationSettings } from "@/components/orchestration-settings";
import { EnvironmentLibrary } from "@/components/environment-library";
import {
  DatabaseConnections,
  type DatabaseConnection,
} from "@/components/database-connections";
import { EnvironmentActions } from "@/components/environment-actions";
import { EnvironmentContext } from "@/components/environment-context";
import { EnvironmentSyncHistory } from "@/components/environment-sync-history";
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
  const { t, dateLocale } = useI18n();
  const searchParams = useSearchParams();
  const router = useRouter();
  const libraryDraft = searchParams.get("library_draft");
  const libraryKind = searchParams.get("library_kind");
  const [tab, setTab] = useState("ai-agents");
  const [sourceTab, setSourceTab] = useState("environments");
  const requestedTab = searchParams.get("tab");
  const requestedSource = searchParams.get("sources");
  useEffect(() => {
    if (requestedTab && ["general", "ai-agents", "environments", "connectors"].includes(requestedTab)) setTab(requestedTab);
    else if (!libraryDraft) setTab("ai-agents");
    if (requestedSource && ["git", "postgres", "environments"].includes(requestedSource)) setSourceTab(requestedSource);
  }, [requestedTab, requestedSource, libraryDraft]);
  const [protocol, setProtocol] = useState("");
  const [guidanceReview, setGuidanceReview] = useState(false);
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
  const [publicationConnections, setPublicationConnections] = useState<number[]>([]);
  const [showEnvironmentForm, setShowEnvironmentForm] = useState(false);
  const [dbId, setDbId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    const version = ++refreshVersion.current;
    const draft = draftVersion.current;
    const [c, e, s, config] = await Promise.all([
      api<Connections>("/connections"),
      api<Environment[]>("/environments"),
      api<typeof settings>("/settings"),
      api<OrchestrationSettings>("/orchestration-settings").catch(() => null),
    ]);
    if (version !== refreshVersion.current) return;
    if (config) { setProtocol(config.reliability_protocol || ""); setGuidanceReview(!!config.preserved_guidance_review); }
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
    { id: "ai-agents", label: t("AI & Agents"), icon: Settings },
    { id: "environments", label: t("Environments"), icon: GitBranch },
    { id: "connectors", label: t("Ticket publication"), icon: Plug },
    { id: "general", label: t("Appearance"), icon: Paintbrush },
  ];
  return (
    <div className="admin-page space-y-6" data-admin-section={tab}>
      <header className="page-heading">
        <div className="page-title">
          <span className="page-icon">
            <Settings size={20} />
          </span>
          <div>
            <h1>{tab === "general" ? t("Settings") : tabs.find(item => item.id === tab)?.label}</h1>
            <p className="muted">
              {t("Connect your tools and prepare analysis environments.")}
            </p>
          </div>
        </div>
        {tab === "environments" && sourceTab === "environments" && <Button onClick={() => { setShowEnvironmentForm(true); requestAnimationFrame(() => document.getElementById("env-name")?.focus()); }}><Plus size={16} aria-hidden="true" />{t("New environment")}</Button>}
      </header>
      <nav
        className="admin-route-nav flex flex-wrap gap-1 border-b pb-3"
        aria-label={t("Administration")}
      >
        {tabs.map((item) => (
          <Button
            key={item.id}
            variant={tab === item.id ? "default" : "ghost"}
            onClick={() => {
              router.replace(`/admin?tab=${item.id}`, { scroll: false });
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
          key={`${libraryKind}:${libraryDraft}:${searchParams.get("connection") || ""}:${searchParams.get("section") || ""}`}
          onChanged={refresh}
          simplified={protocol === "2.4"}
        />
      )}
      {tab === "environments" && (
        <div className="space-y-6">
          <nav className="flex flex-wrap gap-2" aria-label={t("Environment settings")}>
            {[["environments", "Configured environments"], ["git", "Manage Git connections"], ["postgres", "Manage PostgreSQL connections"]].map(([id, label]) =>
              <Button key={id} variant={sourceTab === id ? "default" : "outline"} aria-pressed={sourceTab === id} onClick={() => setSourceTab(id)}>{t(label)}</Button>)}
          </nav>
          {sourceTab === "git" && <GitSources />}
          {sourceTab === "postgres" && <DatabaseConnections values={connections?.databases || []} onChanged={refresh} />}
          {sourceTab === "environments" && <>
          {environments.map((e) => (
            <Card key={e.id} className="environment-card">
              <div className="flex flex-wrap justify-between gap-3">
                <div className="title-tags">
                  <h2 className="flex items-center gap-2"><Database size={22} className="environment-logo" aria-hidden="true" />{e.name}</h2>
                  <span className="badge" data-state={e.status}>
                    {t(({ READY: "Synchronized", PENDING: "Synchronization queued", SYNCING: "Synchronizing", ERROR: "Synchronization failed" } as Record<string, string>)[e.status] || statuses[e.status] || e.status)}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-3">
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
              {e.synced_at && <p className="mt-2 text-xs muted">{t("Last synchronization")}: {new Date(e.synced_at).toLocaleString(dateLocale)}</p>}
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="muted">
                    <tr>
                      <th className="pb-2 pr-4">{t("Project")}</th>
                      <th className="pb-2 pr-4">{t("Branch / tag")}</th>
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
                <details className="mt-3 text-sm"><summary className="cursor-pointer">{t("Synchronization failed")}</summary><pre className="mt-2 whitespace-pre-wrap break-words text-xs">{e.error}</pre></details>
              )}
              <PublicationConnectionsSummary values={e.publication_connections || []} />
              <EnvironmentContext environmentId={e.id} factualOnly={protocol === "2.4"} />
              <EnvironmentSyncHistory environmentId={e.id} />
              {protocol !== "2.4" && <EnvironmentLibrary environmentId={e.id} />}
            </Card>
          ))}
          {showEnvironmentForm && <Card>
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
                    publication_connection_ids: publicationConnections,
                    repositories: selection.map(sourcePayload),
                  });
                  setEnvName("");
                  setPublicationConnections([]);
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
              <PublicationConnectionPicker selected={publicationConnections} onChange={setPublicationConnections} disabled={busy} />
              <Button
                className="mt-5"
                disabled={busy || duplicateSources(selection)}
              >
                {t("Create environment")}
              </Button>
              <Button className="mt-5 ml-3" type="button" variant="ghost" onClick={() => setShowEnvironmentForm(false)}>{t("Cancel")}</Button>
            </form>
          </Card>}
          </>}
        </div>
      )}
      {tab === "connectors" && <div className="space-y-6">
        <TicketConnectors />
      </div>}
      {tab === "general" && (
        <div className="space-y-6">
        <Card className="max-w-2xl">
          <ThemeControl />
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
                  {t("Instance subtitle (optional)")}
                </label>
                <Input
                  id="instance-label"
                  maxLength={80}
                  value={settings.short_label || ""}
                  onChange={(e) =>
                    updateSettings({ short_label: e.target.value })
                  }
                />
                <p className="mt-1 text-xs muted">{t("A short subtitle shown below the instance name.")}</p>
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
        {guidanceReview && <p role="status" className="rounded-lg border p-4 text-sm">{t("Previous custom guidance was preserved for review. Check custom skills and the deployment migration notes before enabling it.")}</p>}
        </div>
      )}
    </div>
  );
}
