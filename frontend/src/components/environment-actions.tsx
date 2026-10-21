"use client";
import { useI18n } from "@/lib/i18n";

import { useEffect, useRef, useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, send, type Environment } from "@/lib/api";

type Selection = {
  repository: string;
  branch: string;
  branches: string[];
  page: number;
  more: boolean;
};
type Database = { id: number; name: string };
type Project = { full_name: string; default_branch: string };

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
  const { t, dateLocale } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"edit" | "review" | "delete" | null>(null);
  const [original, setOriginal] = useState(value);
  const [name, setName] = useState("");
  const [database, setDatabase] = useState("");
  const [selection, setSelection] = useState<Selection[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectPage, setProjectPage] = useState(0);
  const [moreProjects, setMoreProjects] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (mode && !dialog.current?.open) dialog.current?.showModal();
    if (!mode && dialog.current?.open) dialog.current.close();
  }, [mode]);
  function open(next: "edit" | "delete") {
    setOriginal(structuredClone(value));
    setName(value.name);
    setDatabase(value.database_id ? String(value.database_id) : "");
    setSelection(
      value.repositories.map((r) => ({
        repository: r.repository,
        branch: r.branch,
        branches: [r.branch],
        page: 0,
        more: true,
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
  async function loadProjects() {
    const page = projectPage + 1;
    const found = await api<Project[]>(`/github/repositories?page=${page}`);
    const normalized = found.map((project) => ({
      ...project,
      full_name: project.full_name.toLowerCase(),
    }));
    setProjects((old) => (page === 1 ? normalized : [...old, ...normalized]));
    setProjectPage(page);
    setMoreProjects(found.length === 100);
  }
  async function versions(index: number, repository: string, page = 1) {
    const found = await api<{ name: string }[]>(
      `/github/branches?repository=${encodeURIComponent(repository)}&page=${page}`,
    );
    setSelection((old) =>
      old.map((row, i) =>
        i !== index
          ? row
          : {
              repository,
              branch:
                repository === row.repository
                  ? row.branch
                  : projects.find((p) => p.full_name === repository)
                      ?.default_branch ||
                    found[0]?.name ||
                    "",
              branches: Array.from(
                new Set([
                  ...(repository === row.repository
                    ? [row.branch]
                    : [
                        projects.find((p) => p.full_name === repository)
                          ?.default_branch ||
                          found[0]?.name ||
                          "",
                      ]),
                  ...(page > 1 ? row.branches : []),
                  ...found.map((b) => b.name),
                ]),
              ),
              page,
              more: found.length === 100,
            },
      ),
    );
  }
  const changes: string[] = [];
  if (name !== original.name)
    changes.push(
      t("Name: {before} → {after}", { before: original.name, after: name }),
    );
  for (const previous of original.repositories) {
    const next = selection.find((r) => r.repository === previous.repository);
    changes.push(
      !next
        ? t("{repository}: removed", { repository: previous.repository })
        : next.branch === previous.branch
          ? t("{repository}: unchanged ({branch})", {
              repository: previous.repository,
              branch: previous.branch,
            })
          : `${previous.repository} : ${previous.branch} → ${next.branch}`,
    );
  }
  for (const next of selection.filter(
    (r) =>
      !original.repositories.some((old) => old.repository === r.repository),
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
  async function save() {
    await send(
      `/environments/${original.id}`,
      {
        name,
        repositories: selection.map(({ repository, branch }) => ({
          repository,
          branch,
        })),
        database_id: database ? Number(database) : null,
        expected_revision: original.revision,
      },
      "PATCH",
    );
    setMode(null);
    await onChanged(t("Changes saved. Preparing the environment."));
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
                if (
                  new Set(selection.map((r) => r.repository.toLowerCase()))
                    .size !== selection.length
                ) {
                  setError(t("Choose each project only once."));
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
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
                <h3>{t("Projects and versions")}</h3>
                {(projectPage === 0 || moreProjects) && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => task(loadProjects)}
                  >
                    {projectPage
                      ? t("More projects")
                      : t("Browse my GitHub projects")}
                  </Button>
                )}
              </div>
              {selection.map((row, index) => (
                <div
                  key={index}
                  className="mt-5 grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]"
                >
                  <div>
                    <label htmlFor={`edit-repo-${value.id}-${index}`}>
                      {t("Project")} {index + 1}
                    </label>
                    <select
                      id={`edit-repo-${value.id}-${index}`}
                      required
                      value={row.repository}
                      disabled={busy}
                      onChange={(e) =>
                        task(() => versions(index, e.target.value))
                      }
                    >
                      <option value="">{t("Choose a project")}</option>
                      {Array.from(
                        new Set(
                          [
                            row.repository,
                            ...projects.map((p) => p.full_name),
                          ].filter(Boolean),
                        ),
                      ).map((project) => (
                        <option key={project}>{project}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor={`edit-version-${value.id}-${index}`}>
                      {t("Version")} {index + 1}
                    </label>
                    <select
                      id={`edit-version-${value.id}-${index}`}
                      required
                      value={row.branch}
                      disabled={busy}
                      onChange={(e) =>
                        setSelection((old) =>
                          old.map((r, i) =>
                            i === index ? { ...r, branch: e.target.value } : r,
                          ),
                        )
                      }
                    >
                      <option value="">{t("Choose a version")}</option>
                      {row.branches.map((branch) => (
                        <option key={branch}>{branch}</option>
                      ))}
                    </select>
                    {row.repository && row.more && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          task(() =>
                            versions(index, row.repository, row.page + 1),
                          )
                        }
                      >
                        {row.page ? t("More versions") : t("Load versions")}
                      </Button>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={busy || selection.length === 1}
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
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-4"
                disabled={busy || selection.length >= 20}
                onClick={() =>
                  setSelection((old) => [
                    ...old,
                    {
                      repository: "",
                      branch: "",
                      branches: [],
                      page: 0,
                      more: false,
                    },
                  ])
                }
              >
                {t("Add a project")}
              </Button>
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
