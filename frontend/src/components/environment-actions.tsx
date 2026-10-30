"use client";
import { useI18n } from "@/lib/i18n";

import { useEffect, useRef, useState } from "react";
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
}: {
  value: Environment;
  databases: Database[];
  disabled: boolean;
  onChanged: (message: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"edit" | "review" | "delete" | null>(null);
  const [original, setOriginal] = useState(value);
  const [name, setName] = useState("");
  const [database, setDatabase] = useState("");
  const [selection, setSelection] = useState<SourceSelection[]>([]);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [publicationConnections, setPublicationConnections] = useState<number[]>([]);
  useEffect(() => {
    if (mode && !dialog.current?.open) dialog.current?.showModal();
    if (!mode && dialog.current?.open) dialog.current.close();
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
  const changes: string[] = [];
  if (name !== original.name)
    changes.push(
      t("Name: {before} → {after}", { before: original.name, after: name }),
    );
  for (const previous of original.repositories) {
    const next = selection.find(
      (r) =>
        (r.git_connection_id || null) ===
          (previous.git_connection_id || null) &&
        (r.remote_id || r.repository) ===
          (previous.remote_id || previous.repository),
    );
    changes.push(
      !next
        ? t("{repository}: removed", {
            repository: previous.path || previous.repository,
          })
        : next.branch === previous.branch
          ? t("{repository}: unchanged ({branch})", {
              repository: previous.path || previous.repository,
              branch: previous.branch,
            })
          : `${previous.path || previous.repository} : ${previous.branch} → ${next.branch}`,
    );
  }
  for (const next of selection.filter(
    (r) =>
      !original.repositories.some(
        (old) =>
          (old.git_connection_id || null) === (r.git_connection_id || null) &&
          (old.remote_id || old.repository) === (r.remote_id || r.repository),
      ),
  ))
    changes.push(
      t("{repository}: added ({branch})", {
        repository: next.repository,
        branch: next.branch,
      }),
    );
  if (database !== String(original.database_id || ""))
    changes.push(
      t("Database: {before} → {after}", {
        before: original.database_name || t("None"),
        after:
          databases.find((d) => String(d.id) === database)?.name || t("None"),
      }),
    );
  if (JSON.stringify([...publicationConnections].sort()) !== JSON.stringify([...(original.publication_connection_ids || [])].sort())) changes.push(t("Publication destinations updated."));
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
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => open("edit")}
        aria-label={t("Edit {name}", { name: value.name })}
      >
        <Pencil size={14} />
        {t("Edit")}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        disabled={disabled}
        onClick={() => open("delete")}
        aria-label={t("Delete {name}", { name: value.name })}
      >
        <Trash2 size={14} />
        {t("Delete")}
      </Button>
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
        <h2 id={`environment-dialog-${value.id}`}>
          {mode === "delete"
            ? t("Delete environment")
            : mode === "review"
              ? t("Review changes")
              : t("Edit environment")}
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
        ) : mode === "review" ? (
          <div>
            <ul className="mt-5 list-disc space-y-3 pl-5 text-sm leading-6">
              {changes.map((change, i) => (
                <li className="break-words" key={i}>
                  {change}
                </li>
              ))}
            </ul>
            <p className="mt-5 text-sm muted">
              {t("Existing requests will retain their references and results.")}
            </p>
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => setMode("edit")}
              >
                {t("Back to form")}
              </Button>
              <Button disabled={busy} onClick={() => task(save)}>
                {t("Confirm changes")}
              </Button>
            </div>
          </div>
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
                setError("");
                setMode("review");
              }}
            >
              <div className="field">
                <label htmlFor={`edit-name-${value.id}`}>
                  {t("Environment name")}
                </label>
                <Input
                  id={`edit-name-${value.id}`}
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
              <div className="mt-6 flex flex-wrap justify-end gap-3">
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => setMode(null)}
                >
                  {t("Cancel")}
                </Button>
                <Button disabled={busy}>{t("Review changes")}</Button>
              </div>
            </form>
          )
        )}
      </dialog>
    </>
  );
}
