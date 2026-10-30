"use client";
import { SkillMetadata } from "@/components/skill-metadata";

import { Fragment, useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Bot,
  Download,
  History,
  Pencil,
  Plus,
  Power,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { LibraryAssistant } from "@/components/library-assistant";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { libraryValidationMessage } from "@/lib/library-validation";
import { assistantName, assistantProviders } from "@/lib/assistant-providers";

export type LibraryDefinition = {
  slug: string;
  name: string;
  objective: string;
  instructions: string;
  enabled: boolean;
  compatibility: string[];
  required_capabilities: string[];
  version: number;
  deleted: boolean;
  skills?: string[];
  expected_checks?: string[];
  built_in?: boolean;
};
type Revision = {
  version: number;
  definition: LibraryDefinition;
  action: string;
  editor: string;
  created_at: string;
};
export type LibraryDraft = Omit<LibraryDefinition, "version" | "deleted"> & {
  expected_version?: number;
};
const blank: LibraryDraft = {
  slug: "",
  name: "",
  objective: "",
  instructions: "",
  enabled: true,
  compatibility: [],
  required_capabilities: [],
  skills: [],
  expected_checks: [],
};
export const libraryCapabilities = [
  ["read_sources", "Read project sources"],
  ["read_attachments", "Read attachments"],
  ["read_database", "Read the business database"],
  ["read_web", "Read official web sources"],
  ["structured_output", "Produce structured results"],
] as const;
export function libraryPayload(item: LibraryDefinition): LibraryDraft {
  return {
    slug: item.slug,
    name: item.name,
    objective: item.objective || item.name,
    instructions: item.instructions,
    enabled: item.enabled,
    compatibility: item.compatibility,
    required_capabilities: item.required_capabilities,
    skills: item.skills || [],
    expected_checks: item.expected_checks || [],
    expected_version: item.version,
  };
}
function toggle(values: string[], value: string) {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

export function AILibrary({ kind }: { kind: "agent" | "skill" }) {
  const { t, dateLocale } = useI18n();
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<LibraryDefinition[]>([]);
  const [skills, setSkills] = useState<LibraryDefinition[]>([]);
  const [draft, setDraft] = useState<LibraryDraft | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [history, setHistory] = useState<{
    name: string;
    slug: string;
    rows: Revision[];
  } | null>(null);
  const [assistant, setAssistant] = useState(false);
  const [importText, setImportText] = useState<string | null>(null);
  const [importPreview, setImportPreview] = useState<{
    valid: boolean;
    errors?: string[];
    definition?: LibraryDraft;
    kind?: string;
  } | null>(null);
  const [restore, setRestore] = useState<{
    slug: string;
    version: number;
  } | null>(null);
  const [remove, setRemove] = useState<LibraryDefinition | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const generation = useRef(0);
  const prefix = `library-${kind}`;
  async function refresh() {
    const version = ++generation.current;
    const [values, required] = await Promise.all([
      api<LibraryDefinition[]>(`/library/${kind}`),
      kind === "agent"
        ? api<LibraryDefinition[]>("/library/skill")
        : Promise.resolve([]),
    ]);
    if (version !== generation.current) return;
    setItems(values);
    setSkills(required);
    setLoading(false);
  }
  useEffect(() => {
    setLoading(true);
    setDraft(null);
    setHistory(null);
    setRemove(null);
    setError("");
    setNotice("");
    setAssistant(false);
    setImportText(null);
    setImportPreview(null);
    setRestore(null);
    refresh().catch((error) => {
      setError(error.message);
      setLoading(false);
    });
    if (
      new URLSearchParams(window.location.search).get("library_kind") ===
        kind &&
      new URLSearchParams(window.location.search).has("library_draft")
    )
      setAssistant(true);
    return () => {
      generation.current += 1;
    };
  }, [kind]);
  async function action(task: () => Promise<unknown>, message = "") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      await refresh();
      setNotice(message);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const Icon = kind === "agent" ? Bot : BookOpen;
  return (
    <Card className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2">
            <Icon size={20} aria-hidden="true" />
            {t(kind === "agent" ? "Agent library" : "Skills")}
          </h2>
          <p className="mt-2 text-sm muted">
            {t(kind === "skill" ? "All active compatible skills are discoverable automatically. Each assistant loads only the skills useful for its current mission." : "One shared library, reusable across environments and supported assistants.")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={busy || loading}
            onClick={() => {
              setAssistant(true);
              setDraft(null);
              setHistory(null);
              setRemove(null);
              setImportText(null);
            }}
          >
            <Sparkles size={16} aria-hidden="true" />
            {t(kind === "agent" ? "Generate an agent" : "Generate a skill")}
          </Button>
          <Button
            variant="outline"
            disabled={busy || loading}
            onClick={() => {
              setDraft({ ...blank });
              setEditing(null);
              setHistory(null);
              setRemove(null);
              setAssistant(false);
            }}
          >
            <Plus size={16} aria-hidden="true" />
            {t(kind === "agent" ? "New agent" : "New skill")}
          </Button>
          <Button
            variant="outline"
            disabled={busy || loading}
            onClick={() => {
              setImportText("");
              setImportPreview(null);
              setAssistant(false);
              setDraft(null);
            }}
          >
            <Upload size={16} aria-hidden="true" />
            {t(kind === "skill" ? "Import skill" : "Import definition")}
          </Button>
        </div>
      </div>
      <p className="text-sm muted">
        {t(
          kind === "skill" ? "Skills contain instructions only. They cannot change sandbox permissions or access credentials." : "Definitions contain instructions only. They cannot change sandbox permissions or access credentials.",
        )}
      </p>
      {error && (
        <div role="alert" className="rounded-md border p-3 text-sm">
          {t(error)}{" "}
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => action(refresh)}
          >
            {t("Retry")}
          </Button>
        </div>
      )}
      {notice && (
        <p role="status" className="text-sm">
          {t(notice)}
        </p>
      )}
      {assistant && (
        <LibraryAssistant
          kind={kind}
          onClose={() => setAssistant(false)}
          onSaved={refresh}
        />
      )}
      {importText !== null && (
        <section
          className="rounded-lg border p-4 space-y-3"
          aria-label={t(kind === "skill" ? "Import skill" : "Import definition")}
        >
          <h3>{t(kind === "skill" ? "Import skill" : "Import definition")}</h3>
          <p className="text-sm muted">
            {t(
              "Paste a declarative JSON export. Imports are saved inactive and cannot install scripts or extensions.",
            )}
          </p>
          <label className="text-sm" htmlFor={`${prefix}-import`}>
            {t("Definition JSON")}
          </label>
          <textarea
            id={`${prefix}-import`}
            className="w-full rounded-md border bg-background p-3 font-mono text-xs"
            rows={8}
            maxLength={50000}
            value={importText}
            onChange={(event) => {
              setImportText(event.target.value);
              setImportPreview(null);
            }}
          />
          {importPreview && (
            <div role="status" className="rounded-md border p-3 text-sm">
              <p>
                {t(
                  importPreview.valid
                    ? "Configuration checks passed."
                    : "Configuration needs changes.",
                )}
              </p>
              {importPreview.errors?.map((value) => (
                <p key={value}>{libraryValidationMessage(value, t)}</p>
              ))}
              {importPreview.definition && (
                <p>
                  {importPreview.definition.name} ·{" "}
                  {importPreview.definition.slug} · {t("Inactive")}
                </p>
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={busy || !importText.trim()}
              onClick={() =>
                action(async () => {
                  let envelope;
                  try {
                    envelope = JSON.parse(importText);
                  } catch {
                    throw new Error("Enter a valid JSON definition.");
                  }
                  if (envelope.kind !== kind)
                    throw new Error(
                      "Choose the matching agent or skill library before importing.",
                    );
                  const current = items.find(
                    (item) => item.slug === envelope.definition?.slug,
                  );
                  const value = await send<{
                    valid: boolean;
                    errors?: string[];
                    definition?: LibraryDraft;
                  }>("/library/import/preview", {
                    ...envelope,
                    definition: {
                      ...envelope.definition,
                      expected_version: current?.version,
                    },
                  });
                  setImportPreview({ ...value, kind: envelope.kind });
                })
              }
            >
              {t("Validate import")}
            </Button>
            <Button
              disabled={
                busy || !importPreview?.valid || importPreview.kind !== kind
              }
              onClick={() =>
                action(async () => {
                  const envelope = JSON.parse(importText);
                  const current = items.find(
                    (item) => item.slug === envelope.definition?.slug,
                  );
                  await send("/library/import", {
                    ...envelope,
                    definition: {
                      ...envelope.definition,
                      expected_version: current?.version,
                    },
                  });
                  setImportText(null);
                  setImportPreview(null);
                }, "Definition imported as an inactive draft.")
              }
            >
              {t("Import as draft")}
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setImportText(null)}
            >
              {t("Cancel")}
            </Button>
          </div>
        </section>
      )}
      {loading && (
        <p role="status" className="text-sm muted">
          {t("Loading library…")}
        </p>
      )}
      {!loading && !items.length && !error && (
        <p className="text-sm muted">
          {t(
            kind === "agent"
              ? "No agents yet. Create an agent to describe a reusable mission."
              : "No skills yet. Create a skill to describe a reusable procedure.",
          )}
        </p>
      )}
      <div className="field"><label htmlFor={`${prefix}-search`}>{t(kind === "skill" ? "Search skills" : "Search agents")}</label><Input id={`${prefix}-search`} type="search" value={search} onChange={event => setSearch(event.target.value)} /></div>
      {items.filter(item => `${item.name} ${item.objective} ${item.slug}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())).sort((a, b) => Number(!!b.built_in) - Number(!!a.built_in)).map((item, index, filtered) => (
        <Fragment key={item.slug}>
        {kind === "skill" && (index === 0 || !!item.built_in !== !!filtered[index - 1].built_in) && <h3 className="pt-3 text-sm font-semibold">{t(item.built_in ? "Built-in skills" : "Custom skills")}</h3>}
        <article className="rounded-lg border p-4" aria-label={item.built_in ? t(item.name) : item.name}>
          <div className="flex flex-col items-start justify-between gap-3 sm:flex-row">
            <div className="min-w-0 flex-1">
              <h3 className="break-words">
                {item.built_in ? t(item.name) : item.name}{" "}
                <span className="text-xs muted">v{item.version}</span>
                {kind === "skill" && <span className="badge ml-2">{t(item.built_in ? "Built-in" : "Custom")}</span>}
              </h3>
              <p className="mt-1 text-sm muted break-words">
                {item.built_in ? t(item.objective || item.name) : item.objective || item.name}
              </p>
              <p className="mt-2 text-xs muted">
                {t(item.enabled ? "Active" : "Inactive")} ·{" "}
                {kind === "agent" && item.compatibility.length
                  ? item.compatibility
                      .map(assistantName)
                      .join(", ")
                  : t("All supported assistants")}
              </p>
            </div>
            <div className="connection-actions">
              {!item.built_in && <Button
                variant="ghost"
                size="sm"

                title={t("Edit {name}", { name: item.name })}
                aria-label={t("Edit {name}", { name: item.name })}
                disabled={busy}
                onClick={() => {
                  setEditing(item.slug);
                  setDraft(libraryPayload(item));
                  setHistory(null);
                  setRemove(null);
                }}
              >
                <Pencil size={16} aria-hidden="true" />{t("Edit")}
              </Button>}
              <details className="action-menu" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
                <summary aria-label={t("More actions for {name}", { name: item.name })}>⋯</summary>
                <div className="action-menu-items" onClick={event => { if (event.target instanceof Element && event.target.closest("button")) { const menu = event.currentTarget.closest("details"); if (menu) { menu.open = false; menu.querySelector("summary")?.focus(); } } }}>
              <Button
                variant="ghost"
                size="sm"
                className="icon-action"
                title={t("Versions of {name}", { name: item.name })}
                aria-label={t("Versions of {name}", { name: item.name })}
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const rows = await api<Revision[]>(
                      `/library/${kind}/${item.slug}/versions`,
                    );
                    setHistory({ name: item.name, slug: item.slug, rows });
                    setDraft(null);
                    setRemove(null);
                    setRestore(null);
                  })
                }
              >
                <History size={16} aria-hidden="true" />{t("Versions")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="icon-action"
                title={t("Export {name}", { name: item.name })}
                aria-label={t("Export {name}", { name: item.name })}
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const envelope = await api(
                      `/library/${kind}/${item.slug}/export`,
                    );
                    const url = URL.createObjectURL(
                      new Blob([JSON.stringify(envelope, null, 2)], {
                        type: "application/json",
                      }),
                    );
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = `${item.slug}.json`;
                    link.click();
                    URL.revokeObjectURL(url);
                  })
                }
              >
                <Download size={16} aria-hidden="true" />{t("Export")}
              </Button>
              {!item.built_in && <Button
                variant="ghost"
                size="sm"
                className="icon-action"
                title={t(
                  item.enabled ? "Deactivate {name}" : "Activate {name}",
                  { name: item.name },
                )}
                aria-label={t(
                  item.enabled ? "Deactivate {name}" : "Activate {name}",
                  { name: item.name },
                )}
                disabled={busy}
                onClick={() =>
                  action(
                    () =>
                      send(
                        `/library/${kind}/${item.slug}`,
                        { ...libraryPayload(item), enabled: !item.enabled },
                        "PUT",
                      ),
                    "Library updated.",
                  )
                }
              >
                <Power size={16} aria-hidden="true" />{t(item.enabled ? "Deactivate" : "Activate")}
              </Button>}
              {!item.built_in && <Button
                variant="ghost"
                size="sm"
                className="icon-action"
                title={t(
                  item.enabled ? "Disable before deleting" : "Delete {name}",
                  { name: item.name },
                )}
                aria-label={t("Delete {name}", { name: item.name })}
                disabled={busy || item.enabled}
                onClick={() => {
                  setRemove(item);
                  setHistory(null);
                  setDraft(null);
                }}
              >
                <Trash2 size={16} aria-hidden="true" />{t("Delete")}
              </Button>}

                </div>
              </details>
            </div>
          </div>
          {item.built_in && <details className="mt-3 text-sm"><summary className="cursor-pointer font-medium">{t("View instructions")}</summary><p className="mt-3 text-xs muted">{t("Maintained by SpecHelper and available automatically when the required tools are authorized.")}</p><pre className="mt-3 whitespace-pre-wrap break-words font-sans text-xs muted">{item.instructions}</pre></details>}
        </article>
        </Fragment>
      ))}
      {remove && (
        <div
          className="rounded-lg border p-4 space-y-3"
          role="group"
          aria-label={t("Confirm deletion")}
        >
          <p className="text-sm">
            {t("Delete {name}? Historical versions will remain available.", {
              name: remove.name,
            })}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={busy}
              onClick={() =>
                action(async () => {
                  await send(
                    `/library/${kind}/${remove.slug}?expected_version=${remove.version}`,
                    undefined,
                    "DELETE",
                  );
                  setRemove(null);
                }, "Definition deleted. Historical versions retained.")
              }
            >
              {t("Confirm deletion")}
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setRemove(null)}
            >
              {t("Cancel")}
            </Button>
          </div>
        </div>
      )}
      {draft && (
        <form
          className="rounded-lg border p-4"
          onSubmit={(event) => {
            event.preventDefault();
            const submitted = {
              ...draft,
              expected_checks: (draft.expected_checks || [])
                .map((value) => value.trim())
                .filter(Boolean),
            };
            action(async () => {
              await send(
                `/library/${kind}${editing ? `/${editing}` : ""}`,
                submitted,
                editing ? "PUT" : "POST",
              );
              setDraft(null);
              setEditing(null);
            }, "Library definition saved.");
          }}
        >
          <h3>
            {t(
              editing
                ? kind === "skill" ? "Edit skill" : "Edit definition"
                : kind === "agent"
                  ? "New agent"
                  : "New skill",
            )}
          </h3>
          <fieldset disabled={busy} className="min-w-0">
            <div className="field">
              <label htmlFor={`${prefix}-slug`}>{t("Identifier")}</label>
              <Input
                id={`${prefix}-slug`}
                required
                disabled={!!editing}
                maxLength={50}
                pattern="[a-z0-9]+(-[a-z0-9]+)*"
                value={draft.slug}
                onChange={(event) =>
                  setDraft({ ...draft, slug: event.target.value })
                }
              />
              <p className="mt-1 text-xs muted">
                {t(
                  "Lowercase letters, numbers and hyphens. The identifier stays unchanged after creation.",
                )}
              </p>
            </div>
            <div className="field">
              <label htmlFor={`${prefix}-name`}>{t("Name")}</label>
              <Input
                id={`${prefix}-name`}
                required
                maxLength={100}
                value={draft.name}
                onChange={(event) =>
                  setDraft({ ...draft, name: event.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor={`${prefix}-objective`}>{t("Objective")}</label>
              <textarea
                id={`${prefix}-objective`}
                className="w-full rounded-md border bg-background p-3 text-sm"
                required
                maxLength={4000}
                rows={3}
                value={draft.objective}
                onChange={(event) =>
                  setDraft({ ...draft, objective: event.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor={`${prefix}-instructions`}>
                {t("Instructions")}
              </label>
              <textarea
                id={`${prefix}-instructions`}
                className="w-full rounded-md border bg-background p-3 text-sm"
                required
                maxLength={12000}
                rows={7}
                value={draft.instructions}
                onChange={(event) =>
                  setDraft({ ...draft, instructions: event.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor={`${prefix}-checks`}>{t("Expected checks")}</label>
              <textarea
                id={`${prefix}-checks`}
                className="w-full rounded-md border bg-background p-3 text-sm"
                rows={3}
                maxLength={12000}
                value={(draft.expected_checks || []).join("\n")}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    expected_checks: event.target.value.split("\n"),
                  })
                }
              />
              <p className="mt-1 text-xs muted">{t("One check per line.")}</p>
            </div>
            <label className="mt-4 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) =>
                  setDraft({ ...draft, enabled: event.target.checked })
                }
              />
              {t("Active")}
            </label>
            {kind === "skill" ? <SkillMetadata definition={draft} /> : <>
            <fieldset className="mt-5 min-w-0">
              <legend className="text-sm font-medium">
                {t("Compatible assistants")}
              </legend>
              <p className="mt-1 text-xs muted">
                {t("Leave all unchecked for all supported assistants.")}
              </p>
              <div className="mt-2 flex flex-wrap gap-4">
                {assistantProviders.map(({ id: value, name: label }) => (
                  <label
                    key={value}
                    className="flex items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={draft.compatibility.includes(value)}
                      onChange={() =>
                        setDraft({
                          ...draft,
                          compatibility: toggle(draft.compatibility, value),
                        })
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="mt-5 min-w-0">
              <legend className="text-sm font-medium">
                {t("Required capabilities")}
              </legend>
              <p className="mt-1 text-xs muted">
                {t(
                  "Requirements check compatibility; they do not grant permissions.",
                )}
              </p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {libraryCapabilities.map(([value, label]) => (
                  <label
                    key={value}
                    className="flex items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={draft.required_capabilities.includes(value)}
                      onChange={() =>
                        setDraft({
                          ...draft,
                          required_capabilities: toggle(
                            draft.required_capabilities,
                            value,
                          ),
                        })
                      }
                    />
                    {t(label)}
                  </label>
                ))}
              </div>
            </fieldset>
            </>}
            {kind === "agent" && (
              <fieldset className="mt-5 min-w-0">
                <legend className="text-sm font-medium">
                  {t("Required skills")}
                </legend>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {skills
                    .filter(
                      (item) =>
                        item.enabled || draft.skills?.includes(item.slug),
                    )
                    .map((skill) => (
                      <label
                        key={skill.slug}
                        className="flex items-start gap-2 text-sm"
                      >
                        <input
                          type="checkbox"
                          checked={draft.skills?.includes(skill.slug) || false}
                          onChange={() =>
                            setDraft({
                              ...draft,
                              skills: toggle(draft.skills || [], skill.slug),
                            })
                          }
                        />
                        <span>
                          {skill.name}
                          {!skill.enabled ? ` · ${t("Inactive")}` : ""}
                        </span>
                      </label>
                    ))}
                </div>
              </fieldset>
            )}
            {editing && (
              <p className="mt-5 text-xs muted">
                {t(
                  "Editing version {version}. Saving creates a new immutable version.",
                  { version: draft.expected_version || 1 },
                )}
              </p>
            )}
            <div className="mt-5 flex flex-wrap gap-2">
              <Button disabled={busy}>{t(kind === "skill" ? "Save skill" : "Save definition")}</Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setDraft(null);
                  setEditing(null);
                }}
              >
                {t("Cancel")}
              </Button>
            </div>
          </fieldset>
        </form>
      )}
      {history && (
        <div className="rounded-lg border p-4 space-y-4">
          <h3>{t("Versions of {name}", { name: history.name })}</h3>
          {history.rows.map((row) => (
            <details key={row.version} className="rounded-md border p-3">
              <summary className="cursor-pointer text-sm">
                v{row.version} ·{" "}
                {t(
                  (
                    {
                      created: "Created",
                      edited: "Edited",
                      deleted: "Deleted",
                      imported: "Imported",
                      restored: "Restored",
                    } as Record<string, string>
                  )[row.action] || row.action,
                )}{" "}
                · {t("Editor")}: {row.editor} ·{" "}
                {new Date(row.created_at).toLocaleString(dateLocale)}
              </summary>
              <div className="mt-3 text-sm space-y-2">
                <p>{row.definition.objective}</p>
                <pre className="whitespace-pre-wrap break-words font-sans">
                  {row.definition.instructions}
                </pre>
                {(row.definition.expected_checks || []).map((check) => (
                  <p key={check}>{check}</p>
                ))}
                {!items.find(item => item.slug === history.slug)?.built_in && <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    busy ||
                    row.version ===
                      items.find((item) => item.slug === history.slug)?.version
                  }
                  onClick={() =>
                    setRestore({ slug: history.slug, version: row.version })
                  }
                >
                  {t("Restore version {version}", { version: row.version })}
                </Button>}
              </div>
            </details>
          ))}
          {restore && (
            <div
              className="space-y-3 rounded-md border p-3"
              role="group"
              aria-label={t("Confirm restoration")}
            >
              <p className="text-sm">
                {t(
                  "Restore version {version} as a new inactive revision? Existing analyses keep their original configuration.",
                  { version: restore.version },
                )}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={busy}
                  onClick={() =>
                    action(async () => {
                      const current = items.find(
                        (item) => item.slug === restore.slug,
                      );
                      await send(`/library/${kind}/${restore.slug}/restore`, {
                        version: restore.version,
                        expected_version: current?.version,
                      });
                      setRestore(null);
                      setHistory(null);
                    }, "Historical definition restored as an inactive revision.")
                  }
                >
                  {t("Confirm restoration")}
                </Button>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => setRestore(null)}
                >
                  {t("Cancel")}
                </Button>
              </div>
            </div>
          )}
          <Button variant="outline" size="sm" onClick={() => setHistory(null)}>
            {t("Close")}
          </Button>
        </div>
      )}
    </Card>
  );
}
