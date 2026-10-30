"use client";
import { GitBranch, Pencil, Plus, RefreshCw, Power, Trash2 } from "lucide-react";
import { ProviderLogo } from "@/components/provider-logo";
import { useEffect, useRef, useState } from "react";
import { api, send, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { ConnectButton } from "@/components/connect-button";

export type GitConnection = {
  id: number;
  name: string;
  provider: "github" | "gitlab";
  base_url: string;
  account: string;
  enabled: boolean;
  status: string;
  error: string;
  has_secret: boolean;
  referenced_environments: number;
};
export function GitSources() {
  const { t } = useI18n();
  const [values, setValues] = useState<GitConnection[]>([]);
  const [showForm, setShowForm] = useState(false);
  const editor = useRef<HTMLFormElement>(null);
  const [editing, setEditing] = useState<GitConnection | null>(null);
  const [form, setForm] = useState({
    name: "",
    provider: "github",
    base_url: "https://github.com",
    secret: "",
    enabled: true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [removing, setRemoving] = useState<GitConnection | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  async function refresh() {
    setValues(await api<GitConnection[]>("/git-connections"));
    window.dispatchEvent(new Event("connections-updated"));
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (removing) dialog.current?.showModal();
    else dialog.current?.close();
  }, [removing]);
  async function action(task: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      await refresh();
      setNotice(t("Connection settings saved."));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (showForm)
      editor.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, [showForm, editing]);
  function reset() {
    setShowForm(false);
    setEditing(null);
    setForm({
      name: "",
      provider: "github",
      base_url: "https://github.com",
      secret: "",
      enabled: true,
    });
  }
  const connectionForm = showForm ? (
        <form
          id="git-source-editor"
          ref={editor}
          className="mt-6 border-t pt-5"
          onSubmit={(event) => {
            event.preventDefault();
            action(async () => {
              await send(
                editing ? `/git-connections/${editing.id}` : "/git-connections",
                form,
                editing ? "PUT" : "POST",
              );
              reset();
            });
          }}
        >
          {error && <p role="alert" className="mb-3 text-sm text-red-700">{t(error)}</p>}
          <h3>{t(editing ? "Edit Git connection" : "New Git connection")}</h3>
          <div className="field">
            <label htmlFor="git-source-name">{t("Connection name")}</label>
            <Input
              id="git-source-name"
              required
              maxLength={100}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="git-source-provider">{t("Provider")}</label>
            <select
              id="git-source-provider"
              disabled={!!editing}
              value={form.provider}
              onChange={(e) =>
                setForm({
                  ...form,
                  provider: e.target.value,
                  base_url:
                    e.target.value === "github"
                      ? "https://github.com"
                      : "https://gitlab.com",
                })
              }
            >
              <option value="github">GitHub</option>
              <option value="gitlab">GitLab</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="git-source-server">{t("Server URL")}</label>
            <Input
              id="git-source-server"
              type="url"
              required
              readOnly={form.provider === "github"}
              aria-describedby="git-source-server-help"
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            />
            <p id="git-source-server-help" className="mt-2 text-xs muted">
              {t(form.provider === "github"
                ? "GitHub connections currently support github.com only. Self-hosted GitLab servers can be configured by selecting GitLab."
                : "Enter your GitLab server URL. Changing servers requires a new token; connections linked to environments or analysis history must be replaced by a new connection.")}
            </p>
          </div>
          {form.provider === "gitlab" && (
            <div className="field">
              <label htmlFor="git-source-secret">
                {t("Read access token")}
              </label>
              <Input
                id="git-source-secret"
                type="password"
                autoComplete="new-password"
                required={!!editing && form.base_url.trim().replace(/\/$/, "") !== editing.base_url}
                value={form.secret}
                onChange={(e) => setForm({ ...form, secret: e.target.value })}
              />
              <p className="mt-2 text-xs muted">
                {t(
                  "Use only read_api and read_repository access. Leave empty to retain an existing token.",
                )}
              </p>
            </div>
          )}
          {form.provider === "github" && (
            <p className="mt-3 text-sm muted">
              {t(
                "Save this connection, then choose Connect with GitHub to authorize it in your browser.",
              )}
            </p>
          )}
          <div className="mt-4 flex flex-wrap justify-end gap-2" data-editor-actions>
            <Button type="button" variant="outline" disabled={busy} onClick={reset}>{t("Cancel")}</Button>
            <Button disabled={busy}>{t(editing ? "Save" : "Add Git connection")}</Button>
          </div>
        </form>
  ) : null;
  return (
    <Card className="settings-section min-w-0" aria-label={t("Git sources")}>
      <div className="section-heading">
        <h2><GitBranch size={18} aria-hidden="true" />{t("Git sources")}</h2>
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-label={t("New Git connection")}
          onClick={() => {
            reset();
            setShowForm(true);
          }}
        >
          <Plus size={15} aria-hidden="true" />{t("Add connection")}
        </Button>
      </div>
      <p className="mt-2 text-sm muted">
        {t(
          "Connect source accounts for read access. Ticket publication permissions are configured separately.",
        )}
      </p>
      <div className="mt-5 space-y-4">
        {values.map((value) => (
          <section
            className="git-connection-card rounded-lg border bg-card p-4"
            key={value.id}
            aria-label={value.account || value.name}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="title-tags min-w-0 flex-1">
              <h3 className="flex items-center gap-2"><ProviderLogo provider={value.provider} />{value.provider === "github" ? "GitHub" : "GitLab"}{value.account ? ` - ${value.account}` : value.name.toLowerCase() !== value.provider ? ` - ${value.name}` : ""}</h3>
              <span
                className="badge"
                data-state={value.enabled ? value.status : "DISCONNECTED"}
              >
                {t(
                  value.enabled
                    ? statuses[value.status] || value.status
                    : "Disabled",
                )}
              </span>
            </div>
            <div className="ml-auto flex shrink-0 items-center gap-2" data-git-actions>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy}
                aria-expanded={showForm && editing?.id === value.id}
                aria-controls="git-source-editor"
                onClick={() => {
                  setError("");
                  setNotice("");
                  if (showForm && editing?.id === value.id) { reset(); return; }
                  setShowForm(true);
                  setEditing(value);
                  setForm({
                    name: value.name,
                    provider: value.provider,
                    base_url: value.base_url,
                    secret: "",
                    enabled: value.enabled,
                  });
                }}
              >
                <Pencil size={16} aria-hidden="true" />{t("Edit")}
              </Button>
              <details className="action-menu" onKeyDown={event => { if (event.key === "Escape" && !(event.target instanceof Element && event.target.closest("dialog"))) { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
                <summary aria-label={t("More actions for {name}", { name: value.name })}>⋯</summary>
                <div className="action-menu-items" onClick={event => { if (event.target instanceof Element && event.target.closest("button") && !event.target.closest("[data-connection-auth]")) { const menu = event.currentTarget.closest("details"); if (menu) { menu.open = false; menu.querySelector("summary")?.focus(); } } }}>
                  {value.provider === "github" && value.status === "CONNECTED" && <ConnectButton provider="github" startPath={`/git-connections/${value.id}/auth/start`} identityLabel={value.name} reconnect onConnected={() => { action(async () => {}); }} />}
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  action(() => send(`/git-connections/${value.id}/test`))
                }
              >
                <RefreshCw size={16} aria-hidden="true" />{t("Test connection")}
              </Button>

              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() =>
                  action(() =>
                    send(
                      `/git-connections/${value.id}`,
                      {
                        name: value.name,
                        provider: value.provider,
                        base_url: value.base_url,
                        enabled: !value.enabled,
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
                onClick={() => {
                  setRemoving(value);
                  setConfirmation("");
                }}
              >
                <Trash2 size={16} aria-hidden="true" />{t("Delete")}
              </Button>

                </div>
              </details>
            </div>
            </div>
            <p className="mt-2 break-all text-sm muted">
              {value.base_url}
            </p>
            {value.error && (
              <p className="mt-2 text-sm text-red-700">{t(value.error)}</p>
            )}
            <div className="mt-3 empty:hidden">
              {value.provider === "github" && value.status !== "CONNECTED" && <ConnectButton provider="github" startPath={`/git-connections/${value.id}/auth/start`} identityLabel={value.name} onConnected={() => { action(async () => {}); }} />}
            </div>
            {editing?.id === value.id && connectionForm}
          </section>
        ))}
      </div>
      {!values.length && (
        <p className="mt-4 text-sm muted">
          {t("No Git source connections yet.")}
        </p>
      )}
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
        aria-label={t("Delete Git connection")}
        onCancel={(e) => {
          e.preventDefault();
          if (!busy) setRemoving(null);
        }}
        className="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-lg overflow-auto rounded-xl border bg-card p-6 text-foreground shadow-xl backdrop:bg-black/40"
      >
        <h2>{t("Delete Git connection")}</h2>
        <p className="mt-4 text-sm">
          {t(
            removing?.referenced_environments
              ? "This connection is used by environments. Confirming disables it and preserves all requests, tickets and historical references."
              : "This removes the unused connection. Requests, tickets and historical references are preserved.",
          )}
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (removing)
              action(async () => {
                await send(
                  `/git-connections/${removing.id}?confirm_name=${encodeURIComponent(confirmation)}`,
                  undefined,
                  "DELETE",
                );
                setRemoving(null);
              });
          }}
        >
          <div className="field">
            <label htmlFor="git-delete-confirm">
              {t("Type the connection name to confirm")}
            </label>
            <Input
              id="git-delete-confirm"
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
              required
            />
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => setRemoving(null)}
            >
              {t("Cancel")}
            </Button>
            <Button disabled={busy || confirmation !== removing?.name}>
              {t("Confirm deletion")}
            </Button>
          </div>
        </form>
      </dialog>
    </Card>
  );
}
