"use client";
import { useI18n } from "@/lib/i18n";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, send, type Environment } from "@/lib/api";
import { PublicationConnectionPicker } from "@/components/publication-connections";

import {
  RepositoryPicker,
  duplicateSources,
  sourcePayload,
  type SourceSelection,
} from "@/components/repository-picker";
type Database = { id: number; name: string };

export function EnvironmentActions({
  value,
  databases,
  disabled,
  onChanged,
  children,
}: {
  children: (actions: ReactNode) => ReactNode;
  value: Environment;
  databases: Database[];
  disabled: boolean;
  onChanged: (message: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"edit" | "delete" | null>(null);
  const [original, setOriginal] = useState(value);
  const [name, setName] = useState("");
  const [database, setDatabase] = useState("");
  const [selection, setSelection] = useState<SourceSelection[]>([]);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [publicationConnections, setPublicationConnections] = useState<number[]>([]);
  useEffect(() => {
    if (mode === "delete" && !dialog.current?.open) dialog.current?.showModal();
    if (mode !== "delete" && dialog.current?.open) dialog.current.close();
  }, [mode]);
  function open(next: "edit" | "delete") {
    setOriginal(structuredClone(value));
    setName(value.name);
    setPublicationConnections([...(value.publication_connection_ids || [])]);
    setDatabase(value.database_id ? String(value.database_id) : "");
    setSelection(
      value.repositories.map((r) => ({
        repository: r.path || r.repository,
        git_connection_id: r.git_connection_id,
        remote_id: r.remote_id,
        branch: r.branch,
        is_fork: r.is_fork,
        parent: r.parent,
      })),
    );
    setConfirmation("");
    setError("");
    setMode(next);
  }
  async function task(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    const saved = await send<Environment>(
      `/environments/${original.id}`,
      {
        name,
        repositories: selection.map(sourcePayload),
        database_id: database ? Number(database) : null,
        expected_revision: original.revision,
        publication_connection_ids: publicationConnections,
      },
      "PATCH",
    );
    setMode(null);
    await onChanged(t(saved.status === "PENDING" ? "Changes saved. Preparing the environment." : "Changes saved."));
  }
  async function remove() {
    await send(
      `/environments/${original.id}`,
      { confirm_name: confirmation, expected_revision: original.revision },
      "DELETE",
    );
    setMode(null);
    await onChanged(
      t("Environment deleted. Requests and results remain available."),
    );
  }
  const panel = (<>
        <h2 id={`environment-dialog-${value.id}`}>
          {t(mode === "delete" ? "Delete environment" : "Edit environment")}
        </h2>
        {error && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {t(error)}
          </p>
        )}
        {mode === "delete" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              task(remove);
            }}
          >
            <p className="mt-4 text-sm leading-6">
              {t("The configuration and local workspace for “")} {original.name}{" "}
              {t(
                "” will be deleted. Requests, results and references will be preserved.",
              )}
            </p>
            <div className="field">
              <label htmlFor={`delete-name-${value.id}`}>
                {t("Type the environment name to confirm")}
              </label>
              <Input
                id={`delete-name-${value.id}`}
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                autoComplete="off"
                required
              />
            </div>
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setMode(null)}
              >
                {t("Cancel")}
              </Button>
              <Button disabled={busy || confirmation !== original.name}>
                {t("Confirm deletion")}
              </Button>
            </div>
          </form>
        ) : (
          mode === "edit" && (
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
                void task(save);
              }}
            >
              <div className="field">
                <label htmlFor={`edit-name-${value.id}`}>
                  {t("Environment name")}
                </label>
                <Input
                  id={`edit-name-${value.id}`}
                  autoFocus
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <RepositoryPicker
                prefix={`edit-source-${value.id}`}
                values={selection}
                onChange={setSelection}
                disabled={busy}
              />
              <a className="mt-2 inline-block text-xs text-primary underline" href="/admin?tab=environments&sources=git" target="_blank" rel="noopener noreferrer">{t("Manage Git connections")}<span className="sr-only"> · {t("Opens in a new tab")}</span></a>
              <div className="field">
                <label htmlFor={`edit-db-${value.id}`}>{t("Database")}</label>
                <select
                  id={`edit-db-${value.id}`}
                  value={database}
                  onChange={(e) => setDatabase(e.target.value)}
                >
                  <option value="">{t("None")}</option>
                  {databases.map((db) => (
                    <option key={db.id} value={db.id}>
                      {db.name}
                    </option>
                  ))}
                </select>
              </div>
              <a className="text-xs text-primary underline" href="/admin?tab=environments&sources=postgres" target="_blank" rel="noopener noreferrer">{t("Manage PostgreSQL connections")}<span className="sr-only"> · {t("Opens in a new tab")}</span></a>
              <PublicationConnectionPicker selected={publicationConnections} onChange={setPublicationConnections} disabled={busy} />
              <div className="mt-4 flex flex-wrap justify-end gap-2" data-editor-actions>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => setMode(null)}
                >
                  {t("Cancel")}
                </Button>
                <Button disabled={busy || disabled}>{t("Save")}</Button>
              </div>
            </form>
          )
        )}
  </>);
  return (
    <>
      {children(<>
      <Button
        variant="outline"
        size="sm"
        disabled={disabled || busy}
        aria-expanded={mode === "edit"}
        aria-controls={`environment-editor-${value.id}`}
        onClick={() => {
          if (mode === "edit") { setMode(null); setError(""); }
          else open("edit");
        }}
        aria-label={t("Edit {name}", { name: value.name })}
      >
        <Pencil size={14} />
        {t("Edit")}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        disabled={disabled || busy}
        onClick={() => open("delete")}
        aria-label={t("Delete {name}", { name: value.name })}
      >
        <Trash2 size={14} />
        {t("Delete")}
      </Button>
      </>)}
      {mode === "edit" && <section
        id={`environment-editor-${value.id}`}
        aria-labelledby={`environment-dialog-${value.id}`}
        className="mt-4 min-w-0 border-t pt-4"
      >{panel}</section>}
      <dialog
        ref={dialog}
        style={{ width: "calc(100% - 2rem)" }}
        aria-labelledby={`environment-dialog-${value.id}`}
        onCancel={(e) => {
          e.preventDefault();
          if (!busy) setMode(null);
        }}
        className="fixed inset-0 m-auto max-h-[90dvh] max-w-2xl overflow-y-auto rounded-xl border bg-card p-6 text-foreground shadow-xl backdrop:bg-black/40"
      >
        {mode === "delete" && panel}
      </dialog>
    </>
  );
}
