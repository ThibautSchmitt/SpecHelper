"use client";
import { Database, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ProviderLogo } from "@/components/provider-logo";
import { send, statuses } from "@/lib/api";
import { useLocalConnectionHost } from "@/lib/ticket-links";

export type DatabaseConnection = {
  id: number;
  name: string;
  status: string;
  checked_at?: string | null;
  host: string;
  database: string;
  port?: number;
  username?: string;
  sslmode?: string;
};
type Probe = {
  status: string;
  checks: { connection: boolean; read: boolean; read_only: boolean };
};
const empty = { name: "", url: "", host: "", port: 5432, database: "", username: "", password: "", sslmode: "require" };

export function DatabaseConnections({ values, onChanged }: {
  values: DatabaseConnection[]; onChanged: () => Promise<void>;
}) {
  const { t, dateLocale } = useI18n();
  const localHost=useLocalConnectionHost();
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState<DatabaseConnection | null>(null);
  const [removing, setRemoving] = useState<DatabaseConnection | null>(null);
  const [useURL, setUseURL] = useState(false);
  const [value, setValue] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [checks, setChecks] = useState<Probe["checks"] | null>(null);
  const editor = useRef<HTMLFormElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (show) editor.current?.querySelector<HTMLInputElement>("input")?.focus(); }, [show, editing]);
  useEffect(() => { if (removing) dialog.current?.showModal(); else dialog.current?.close(); }, [removing]);
  function reset() {
    setShow(false); setEditing(null); setUseURL(false); setValue(empty); setError("");
  }
  async function save() {
    setBusy(true); setError(""); setChecks(null); setNotice("");
    try {
      const result = await send<Probe>(editing ? "/connections/databases/" + editing.id : "/connections/databases",
        { ...value, url: useURL ? value.url : "", host: useURL ? "" : value.host }, editing ? "PUT" : "POST");
      setChecks(result.checks);
      await onChanged();
      reset();
      setNotice(t("Connection settings saved."));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function probe(id: number) {
    setBusy(true); setError(""); setChecks(null); setNotice("");
    try {
      const result = await send<Probe>("/connections/databases/" + id + "/test");
      setChecks(result.checks);
      await onChanged();
    } catch (e) {
      setError((e as Error).message);
      try { await onChanged(); } catch {}
    } finally { setBusy(false); }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true); setError(""); setChecks(null); setNotice("");
    try {
      await send("/connections/databases/" + removing.id, undefined, "DELETE");
      await onChanged();
      setRemoving(null);
      if (editing?.id === removing.id) reset();
      setNotice(t("Connection deleted."));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const connectionForm = show ? (
        <form
          id="database-connection-editor"
          ref={editor}
          className="mt-4 border-t pt-4"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <fieldset disabled={busy} className="min-w-0">
          <h3>{t(editing ? "Edit PostgreSQL connection" : "Add connection")}</h3>
          {error && <p role="alert" className="mt-3 text-sm text-red-700">{t(error)}</p>}
          <div className="field">
            <label htmlFor="db-name">{t("Connection name")}</label>
            <Input
              id="db-name"
              required
              maxLength={100}
              value={value.name}
              onChange={(e) => setValue({ ...value, name: e.target.value })}
            />
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useURL}
              onChange={(e) => { setUseURL(e.target.checked); if (e.target.checked && editing) setValue({ ...value, username: "" }); }}
            />
            {t("Use a PostgreSQL URL")}
          </label>
          {useURL ? (
            <div className="field">
              <label htmlFor="db-url">{t("PostgreSQL URL")}</label>
              <Input
                id="db-url"
                type="password"
                required
                maxLength={2048}
                autoComplete="off"
                placeholder={t("postgresql://host/database")}
                value={value.url}
                onChange={(e) => setValue({ ...value, url: e.target.value })}
              />
              <p className="mt-2 text-xs muted">
                {t(
                  "The username and password can be included in the URL or entered below.",
                )}
              </p>
            </div>
          ) : (
            <div className="grid gap-x-5 sm:grid-cols-2">
              {[
                { key: "host", label: t("Host") },
                { key: "port", label: t("Port") },
                { key: "database", label: t("Database") },
              ].map((field) => (
                <div className="field" key={field.key}>
                  <label htmlFor={`db-${field.key}`}>{t(field.label)}</label>
                  <Input
                    id={`db-${field.key}`}
                    required
                    type={field.key === "port" ? "number" : "text"}
                    value={value[field.key as "host" | "port" | "database"]}
                    onChange={(e) =>
                      setValue({
                        ...value,
                        [field.key]:
                          field.key === "port"
                            ? Number(e.target.value)
                            : e.target.value,
                      })
                    }
                  />
                </div>
              ))}
            </div>
          )}
          <p className="mt-2 text-xs muted">{t("Use the PostgreSQL host and port, such as localhost:5432. Adminer is a separate web interface.")}</p>
          <div className="grid gap-x-5 sm:grid-cols-2">
            <div className="field">
              <label htmlFor="db-username">{t("PostgreSQL username")}</label>
              <Input
                id="db-username"
                required={!useURL}
                maxLength={100}
                value={value.username}
                onChange={(e) =>
                  setValue({ ...value, username: e.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor="db-password">{t("Password")}</label>
              <Input
                id="db-password"
                type="password"
                required={!editing && !useURL}
                maxLength={1000}
                autoComplete="new-password"
                aria-describedby={editing ? "db-password-help" : undefined}
                value={value.password}
                onChange={(e) =>
                  setValue({ ...value, password: e.target.value })
                }
              />
            </div>
          </div>
          {editing && <p id="db-password-help" className="mt-2 text-xs muted">{t("Leave the password blank to keep the saved password.")}</p>}
          <div className="field">
            <label htmlFor="db-sslmode">{t("TLS encryption")}</label>
            <select
              id="db-sslmode"
              value={value.sslmode}
              onChange={(e) => setValue({ ...value, sslmode: e.target.value })}
            >
              <option value="require">{t("Require TLS")}</option>
              <option value="verify-full">
                {t("Verify certificate and host")}
              </option>
              <option value="verify-ca">{t("Verify certificate")}</option>
              <option value="disable">{t("Disabled (local network)")}</option>
            </select>
          </div>
          <div className="mt-4 flex flex-wrap justify-end gap-2" data-editor-actions>
            <Button type="button" variant="outline" disabled={busy} onClick={reset}>{t("Cancel")}</Button>
            <Button disabled={busy}>{busy ? t("Verifying…") : t("Save")}</Button>
          </div>
          <p className="mt-2 text-xs muted">
            {t("A verified connection is saved for your environments.")}
          </p>
          </fieldset>
        </form>
  ) : null;
  return <section className="min-w-0" aria-label={t("PostgreSQL connections")}>
    <div className="section-heading">
      <h2><Database size={18} aria-hidden="true" />{t("PostgreSQL connections")}</h2>
      <Button type="button" size="sm" variant="outline" disabled={busy} aria-expanded={show && !editing}
        aria-controls="database-connection-editor" onClick={() => {
          const close = show && !editing;
          reset(); setChecks(null); setNotice(""); if (!close) setShow(true);
        }}><Plus size={15} aria-hidden="true" />{t("Add connection")}</Button>
    </div>
    <p className="mt-2 text-sm muted">{t("Associate a database with an environment only if the analysis needs it. Use read-only access.")}</p>
    {show && !editing && connectionForm}
    <div className="mt-5 space-y-4">{values.map(database => <section key={database.id}
      className="database-connection-card rounded-lg border bg-card p-4" aria-label={database.name}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="title-tags min-w-0 flex-1">
          <h3 className="flex min-w-0 items-center gap-2"><ProviderLogo provider="postgresql" /><span className="break-words">{database.name}</span></h3>
          <span className="badge" data-state={database.status}>{t(database.status === "ERROR" ? "Connection failed" : statuses[database.status] || "Unknown")}</span>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2" data-database-actions>
          <Button type="button" size="sm" variant="outline" disabled={busy} aria-expanded={show && editing?.id === database.id}
            aria-controls="database-connection-editor" onClick={() => {
              if (show && editing?.id === database.id) { reset(); return; }
              setChecks(null); setError(""); setNotice(""); setUseURL(false); setEditing(database); setShow(true);
              setValue({ ...empty, name: database.name, host: localHost(database.host), port: database.port ?? 5432,
                database: database.database, username: database.username || "", sslmode: database.sslmode || "require" });
            }}><Pencil size={16} aria-hidden="true" />{t("Edit")}</Button>
          <details className="action-menu" onKeyDown={event => {
            if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); }
          }}>
            <summary aria-label={t("More actions for {name}", { name: database.name })}>⋯</summary>
            <div className="action-menu-items" onClick={event => {
              if (event.target instanceof Element && event.target.closest("button")) {
                const menu = event.currentTarget.closest("details"); if (menu) { menu.open = false; menu.querySelector("summary")?.focus(); }
              }
            }}>
              <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => probe(database.id)}>
                <RefreshCw size={16} aria-hidden="true" />{t("Test connection")}
              </Button>
              <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => { setError(""); setRemoving(database); }}>
                <Trash2 size={16} aria-hidden="true" />{t("Delete")}
              </Button>
            </div>
          </details>
        </div>
      </div>
      <p className="mt-2 break-words text-sm muted">{localHost(database.host)}:{database.port ?? 5432} · {database.database}</p>
      <p className="mt-1 text-xs muted">{t("Last checked")}: {database.checked_at ? new Date(database.checked_at).toLocaleString(dateLocale) : t("Verification date not recorded")}</p>
      {show && editing?.id === database.id && connectionForm}
    </section>)}</div>
    {(checks || notice) && <div role="status" className="mt-4 space-y-2 text-sm text-green-800">
      {notice && <p>{notice}</p>}
      {checks && <div className="flex flex-wrap gap-3">
        {checks.connection && <span>{t("✓ Connection OK")}</span>}
        {checks.read && <span>{t("✓ Read query OK")}</span>}
        {checks.read_only && <span>{t("✓ Read-only")}</span>}
      </div>}
    </div>}
    {error && !show && !removing && <p role="alert" className="mt-4 text-sm text-red-700">{t(error)}</p>}
    <dialog ref={dialog} className="modal" aria-labelledby="database-delete-title"
      onCancel={event => { if (busy) event.preventDefault(); else { setRemoving(null); setError(""); } }}>
      <h2 id="database-delete-title">{t("Delete PostgreSQL connection")}</h2>
      <p className="mt-3 text-sm">{t("Delete this PostgreSQL connection? Connections used by an environment or analysis history cannot be deleted.")}</p>
      {removing && <p className="mt-2 font-medium">{removing.name}</p>}
      {error && removing && <p role="alert" className="mt-3 text-sm text-red-700">{t(error)}</p>}
      <div className="mt-5 flex justify-end gap-2">
        <Button type="button" variant="outline" disabled={busy} onClick={() => { setRemoving(null); setError(""); }}>{t("Cancel")}</Button>
        <Button type="button" disabled={busy} onClick={() => void remove()}>{t("Confirm deletion")}</Button>
      </div>
    </dialog>
  </section>;
}
