"use client";
import { SkillMetadata } from "@/components/skill-metadata";

import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import {
  BookOpen,
  ChevronDown,
  Bot,
  Download,
  History,
  Pencil,
  Plus,
  Power,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
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

/** The library uses the same native modal behavior as the other settings dialogs. */
function SkillDrawer({ title, busy, onClose, children }: {
  title: string; busy: boolean; onClose: () => void; children: ReactNode;
}) {
  const { t } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const panel = dialog.current;
    panel?.showModal();
    panel?.querySelector<HTMLElement>("input:not([disabled]), textarea:not([disabled])")?.focus();
    return () => { panel?.close(); if (opener?.isConnected) opener.focus(); };
  }, []);
  return <dialog ref={dialog} aria-labelledby="skill-drawer-title" className="skill-drawer"
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}
    onClick={event => { if (event.target === event.currentTarget && !busy) {
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
    } }}>
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b p-5">
        <h2 id="skill-drawer-title" className="text-lg">{title}</h2>
        <Button type="button" size="sm" variant="ghost" className="shrink-0" disabled={busy} aria-label={t("Close")} onClick={onClose}><X size={18} aria-hidden="true" /></Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-5">{children}</div>
    </div>
  </dialog>;
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
  const draftBaseline = useRef("");
  const importFile = useRef<HTMLInputElement>(null);
  const [assistantState, setAssistantState] = useState({ unsaved: false, busy: false });
  const drawerOpen = kind === "skill" && (!!draft || assistant || importText !== null);
  function closePanel() {
    if (busy || assistant && assistantState.busy) return;
    const dirty = draft ? JSON.stringify(draft) !== draftBaseline.current : assistant ? assistantState.unsaved : !!importText?.trim();
    if (kind === "skill" && dirty && !window.confirm(t("Discard unsaved skill changes?"))) return;
    setDraft(null); setEditing(null); setAssistant(false); setImportText(null); setImportPreview(null); setError("");
  }
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
  const visibleItems = items.filter(item => [item.name, item.objective, item.slug,
    ...(item.built_in ? [t(item.name), t(item.objective)] : []),
  ].join(" ").toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
    .sort((a, b) => Number(!!a.built_in) - Number(!!b.built_in));
  const definitionForm = draft ? (
        <form
          id={draft.slug ? `${prefix}-editor-${draft.slug}` : `${prefix}-editor-new`}
          className={kind === "skill" ? "min-w-0" : "mt-4 min-w-0 border-t pt-4"}
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
          {kind === "agent" && <h3>
            {t(
              editing
                ? "Edit definition"
                : kind === "agent"
                  ? "New agent"
                  : "New skill",
            )}
          </h3>}
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
            {editing && kind === "agent" && (
              <p className="mt-5 text-xs muted">
                {t(
                  "Editing version {version}. Saving creates a new immutable version.",
                  { version: draft.expected_version || 1 },
                )}
              </p>
            )}
            <div className={kind === "skill" ? "sticky bottom-0 -mx-5 -mb-5 mt-5 flex flex-wrap justify-end gap-2 border-t bg-card p-4" : "mt-5 flex flex-wrap justify-end gap-2"} data-editor-actions>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={closePanel}
              >
                {t("Cancel")}
              </Button>
              <Button disabled={busy}>{t(editing ? "Save" : kind === "skill" ? "Save skill" : "Save definition")}</Button>
            </div>
          </fieldset>
        </form>
  ) : null;
  const importForm = importText !== null ? (
        <section
          className={kind === "skill" ? "space-y-3" : "rounded-lg border p-4 space-y-3"}
          aria-label={t(kind === "skill" ? "Import skill" : "Import definition")}
        >
          {kind === "agent" && <h3>{t("Import definition")}</h3>}
          <p className="text-sm muted">
            {t(
              "Paste a declarative JSON export. Imports are saved inactive and cannot install scripts or extensions.",
            )}
          </p>
          {kind === "skill" && <>
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => importFile.current?.click()}><Upload size={15} aria-hidden="true" />{t("Select a JSON file")}</Button>
            <input ref={importFile} type="file" accept=".json,application/json" hidden aria-label={t("Select a JSON file")}
              onChange={async event => {
                const file = event.target.files?.[0]; event.target.value = "";
                if (!file) return;
                setError(""); setImportPreview(null); setBusy(true);
                try {
                  if (file.size > 200000) throw new Error("The import is limited to 50,000 characters.");
                  const content = await file.text();
                  if (content.length > 50000) throw new Error("The import is limited to 50,000 characters.");
                  setImportText(content); setImportPreview(null);
                } catch (error) { setError((error as Error).message); }
                finally { setBusy(false); }
              }} />
          </>}
          <label className="text-sm" htmlFor={`${prefix}-import`}>
            {t("Definition JSON")}
          </label>
          <textarea
            id={`${prefix}-import`}
            className="w-full rounded-md border bg-background p-3 font-mono text-xs"
            rows={8}
            maxLength={50000}
            disabled={busy}
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
              onClick={closePanel}
            >
              {t("Cancel")}
            </Button>
          </div>
        </section>
       ) : null;
  return (
    <section className="min-w-0 space-y-5" aria-label={t(kind === "agent" ? "Agent library" : "Skills")}>
      <header>
        <div className="section-heading">
          <h2><Icon size={18} aria-hidden="true" />{t(kind === "agent" ? "Agent library" : "Skills")}</h2>
          <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            type="button"
            size="sm"
            aria-label={t(kind === "agent" ? "Add agent" : "Add skill")}
            variant="outline"
            disabled={busy || loading}
            onClick={() => {
              draftBaseline.current = JSON.stringify(blank);
              setError(""); setNotice(""); setImportText(null); setImportPreview(null);
              setDraft({ ...blank });
              setEditing(null);
              setHistory(null);
              setRemove(null);
              setAssistant(false);
            }}
          >
            <Plus size={16} aria-hidden="true" />
            {t(kind === "agent" ? "Add agent" : "Add skill")}
          </Button>

          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy || loading}
            onClick={() => {
              setError(""); setNotice(""); setAssistantState({unsaved:false, busy:false});
              setAssistant(true);
              setDraft(null);
              setHistory(null);
              setRemove(null);
              setImportText(null);
            }}
          >
            <Sparkles size={16} aria-hidden="true" />
            {t(kind === "agent" ? "Generate an agent" : "Generate with AI")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy || loading}
            onClick={() => {
              setError(""); setNotice("");
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
      <p className="mt-2 text-sm muted">{t(kind === "skill" ? "Skills give AI assistants specialized methods. Built-in skills are automatic; you can add your own." : "One shared library, reusable across environments and supported assistants.")}</p>
      </header>
      <Card data-skill-library-content className={"settings-section min-w-0 space-y-4" + (kind === "skill" ? " skill-library-panel" : "")}>
      <details className="text-xs muted"><summary className="cursor-pointer">{t("About skill permissions")}</summary><p className="mt-2">{t("Skills guide AI assistants without changing their access permissions.")}</p></details>
      {error && !drawerOpen && (
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
      {kind === "agent" && assistant && (
        <LibraryAssistant
          kind={kind}
          onClose={() => setAssistant(false)}
          onSaved={refresh}
        />
      )}
      {kind === "agent" && importForm}
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
      <div className="relative w-full sm:max-w-xs">
        <label className="sr-only" htmlFor={`${prefix}-search`}>{t(kind === "skill" ? "Search skills" : "Search agents")}</label>
        <Search size={15} className="pointer-events-none absolute left-3 top-3 muted" aria-hidden="true" />
        <Input className="pl-9" id={`${prefix}-search`} type="search" placeholder={t("Search skills…")} value={search} onChange={event => setSearch(event.target.value)} />
      </div>
      {kind === "skill" && !loading && !error && !visibleItems.some(item => !item.built_in) && <section aria-label={t("Custom skills")} className="pt-2"><h3 className="text-sm font-semibold">{t("Custom skills")}</h3><p className="mt-1 text-xs muted">{t("Skills added to this instance.")}</p><p className="mt-3 text-sm muted">{t(search.trim() ? "No matching skills." : "No custom skills.")}</p></section>}
      {kind === "agent" && !loading && search.trim() && !visibleItems.length && <p role="status" className="text-sm muted">{t("No matching skills.")}</p>}
      {visibleItems.map((item, index, filtered) => (
        <Fragment key={item.slug}>
        {kind === "skill" && (index === 0 || !!item.built_in !== !!filtered[index - 1].built_in) && <div className="pt-3"><h3 className="text-sm font-semibold">{t(item.built_in ? "Built-in skills" : "Custom skills")}</h3><p className="mt-1 text-xs muted">{t(item.built_in ? "Provided and used automatically by SpecHelper." : "Skills added to this instance.")}</p></div>}
        {kind === "skill" && item.built_in ? <details className="group border-b py-3 last:border-b-0" data-builtin-skill>
          <summary className="flex cursor-pointer list-none items-start gap-3" aria-label={t("View instructions") + " — " + t(item.name)}>
            <BookOpen size={17} className="mt-1 shrink-0 muted" aria-hidden="true" />
            <span className="min-w-0 flex-1"><span className="block text-sm font-medium">{t(item.name)}</span><span className="mt-1 line-clamp-2 block text-xs muted">{t(item.objective || item.name)}</span></span>
            <span className="badge shrink-0">{t("Built-in")}</span><ChevronDown size={16} className="mt-1 shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
          </summary>
          <pre className="mt-3 whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-sans text-xs">{item.instructions}</pre>
        </details> : <article className={kind === "skill" ? "border-b py-3 last:border-b-0" : "rounded-lg border p-4"} aria-label={item.built_in ? t(item.name) : item.name}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="title-tags"><h3 className={kind === "skill" ? "break-words text-sm font-medium" : "break-words"}>
                {item.built_in ? t(item.name) : item.name}{" "}
                {kind === "agent" && !item.built_in && <span className="text-xs muted">v{item.version}</span>}
              </h3>
                {kind === "skill" && <span className="badge">{t(item.enabled ? "Active" : "Inactive")}</span>}
              </div>
              <p className="mt-1 line-clamp-2 text-sm muted break-words">
                {item.built_in ? t(item.objective || item.name) : item.objective || item.name}
              </p>
              {kind === "agent" && !item.built_in && <p className="mt-2 text-xs muted">
                {t(item.enabled ? "Active" : "Inactive")} ·{" "}
                {kind === "agent" && item.compatibility.length
                  ? item.compatibility
                      .map(assistantName)
                      .join(", ")
                  : t("All supported assistants")}
              </p>}
            </div>
            <div className="connection-actions">
              {!item.built_in && <Button
                variant="ghost"
                size="sm"

                title={t("Edit {name}", { name: item.name })}
                aria-label={t("Edit {name}", { name: item.name })}
                disabled={busy}
                aria-expanded={!!draft && editing === item.slug}
                aria-controls={`${prefix}-editor-${item.slug}`}
                onClick={() => {
                  setError("");
                  if (draft && editing === item.slug) { setDraft(null); setEditing(null); return; }
                  setEditing(item.slug);
                  draftBaseline.current = JSON.stringify(libraryPayload(item));
                  setAssistant(false); setImportText(null); setImportPreview(null);
                  setDraft(libraryPayload(item));
                  setHistory(null);
                  setRemove(null);
                }}
              >
                <Pencil size={16} aria-hidden="true" />{t("Edit")}
              </Button>}
              {!item.built_in && <details className="action-menu" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
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
              </details>}
            </div>
          </div>
          {item.built_in && <details className="mt-3 text-sm"><summary className="cursor-pointer font-medium">{t("View instructions")}</summary><pre className="mt-3 whitespace-pre-wrap break-words font-sans text-xs muted">{item.instructions}</pre></details>}
          {kind === "skill" && <details className="mt-2 text-xs"><summary className="cursor-pointer muted">{t("View instructions")}</summary><pre className="mt-3 whitespace-pre-wrap break-words font-sans">{item.instructions}</pre></details>}
          {kind === "agent" && editing === item.slug && definitionForm}
        </article>}
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
      {kind === "agent" && !editing && definitionForm}
      {drawerOpen && <SkillDrawer title={t(draft ? editing ? "Edit skill" : "New skill" : assistant ? "Generate with AI" : "Import skill")}
        busy={busy || assistant && assistantState.busy} onClose={closePanel}>
        {error && <p role="alert" className="mb-4 rounded-md border p-3 text-sm">{t(error)}</p>}
        {draft ? definitionForm : assistant ? <LibraryAssistant kind={kind} onClose={closePanel} onSaved={refresh} onCloseStateChange={setAssistantState} embedded /> : importForm}
      </SkillDrawer>}
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
    </section>
  );
}
