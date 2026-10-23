"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, Bot, History, Pencil, Plus, Power, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

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
};
type Revision = { version: number; definition: LibraryDefinition; action: string; editor: string; created_at: string };
type Draft = Omit<LibraryDefinition, "version" | "deleted"> & { expected_version?: number };
const blank: Draft = { slug: "", name: "", objective: "", instructions: "", enabled: true, compatibility: [], required_capabilities: [], skills: [] };
const capabilities = [
  ["read_sources", "Read project sources"],
  ["read_attachments", "Read attachments"],
  ["read_database", "Read the business database"],
  ["structured_output", "Produce structured results"],
] as const;
export function libraryPayload(item: LibraryDefinition): Draft {
  return {
    slug: item.slug, name: item.name, objective: item.objective || item.name,
    instructions: item.instructions, enabled: item.enabled,
    compatibility: item.compatibility, required_capabilities: item.required_capabilities,
    skills: item.skills || [], expected_version: item.version,
  };
}
function toggle(values: string[], value: string) {
  return values.includes(value) ? values.filter(item => item !== value) : [...values, value];
}

export function AILibrary({ kind }: { kind: "agent" | "skill" }) {
  const { t, dateLocale } = useI18n();
  const [items, setItems] = useState<LibraryDefinition[]>([]);
  const [skills, setSkills] = useState<LibraryDefinition[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [history, setHistory] = useState<{ name: string; rows: Revision[] } | null>(null);
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
      kind === "agent" ? api<LibraryDefinition[]>("/library/skill") : Promise.resolve([]),
    ]);
    if (version !== generation.current) return;
    setItems(values); setSkills(required); setLoading(false);
  }
  useEffect(() => {
    setLoading(true); setDraft(null); setHistory(null); setRemove(null); setError(""); setNotice("");
    refresh().catch(error => { setError(error.message); setLoading(false); });
    return () => { generation.current += 1; };
  }, [kind]);
  async function action(task: () => Promise<unknown>, message = "") {
    setBusy(true); setError(""); setNotice("");
    try { await task(); await refresh(); setNotice(message); }
    catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  const Icon = kind === "agent" ? Bot : BookOpen;
  return (
    <Card className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2"><Icon size={20} aria-hidden="true" />{t(kind === "agent" ? "Agent library" : "Skill library")}</h2>
          <p className="mt-2 text-sm muted">{t("One shared library, reusable across environments and supported assistants.")}</p>
        </div>
        <Button disabled={busy || loading} onClick={() => { setDraft({ ...blank }); setEditing(null); setHistory(null); setRemove(null); }}><Plus size={16} aria-hidden="true" />{t(kind === "agent" ? "New agent" : "New skill")}</Button>
      </div>
      <p className="text-sm muted">{t("Definitions contain instructions only. They cannot change sandbox permissions or access credentials.")}</p>
      {error && <div role="alert" className="rounded-md border p-3 text-sm">{t(error)} <Button size="sm" variant="ghost" disabled={busy} onClick={() => action(refresh)}>{t("Retry")}</Button></div>}
      {notice && <p role="status" className="text-sm">{t(notice)}</p>}
      {loading && <p role="status" className="text-sm muted">{t("Loading library…")}</p>}
      {!loading && !items.length && !error && <p className="text-sm muted">{t(kind === "agent" ? "No agents yet. Create an agent to describe a reusable mission." : "No skills yet. Create a skill to describe a reusable procedure.")}</p>}
      {items.map(item => (
        <article key={item.slug} className="rounded-lg border p-4">
          <div className="flex flex-col items-start justify-between gap-3 sm:flex-row">
            <div className="min-w-0 flex-1">
              <h3 className="break-words">{item.name} <span className="text-xs muted">v{item.version}</span></h3>
              <p className="mt-1 text-sm muted break-words">{item.objective || item.name}</p>
              <p className="mt-2 text-xs muted">{t(item.enabled ? "Active" : "Inactive")} · {item.compatibility.length ? item.compatibility.map(value => value === "codex" ? "ChatGPT / Codex" : "Claude Code").join(", ") : t("All supported assistants")}</p>
            </div>
            <div className="connection-actions">
              <Button variant="ghost" size="sm" className="icon-action" title={t("Edit {name}", { name: item.name })} aria-label={t("Edit {name}", { name: item.name })} disabled={busy} onClick={() => { setEditing(item.slug); setDraft(libraryPayload(item)); setHistory(null); setRemove(null); }}><Pencil size={16} aria-hidden="true" /></Button>
              <Button variant="ghost" size="sm" className="icon-action" title={t("Versions of {name}", { name: item.name })} aria-label={t("Versions of {name}", { name: item.name })} disabled={busy} onClick={() => action(async () => { const rows = await api<Revision[]>(`/library/${kind}/${item.slug}/versions`); setHistory({ name: item.name, rows }); setDraft(null); setRemove(null); })}><History size={16} aria-hidden="true" /></Button>
              <Button variant="ghost" size="sm" className="icon-action" title={t(item.enabled ? "Deactivate {name}" : "Activate {name}", { name: item.name })} aria-label={t(item.enabled ? "Deactivate {name}" : "Activate {name}", { name: item.name })} disabled={busy} onClick={() => action(() => send(`/library/${kind}/${item.slug}`, { ...libraryPayload(item), enabled: !item.enabled }, "PUT"), "Library updated.")}><Power size={16} aria-hidden="true" /></Button>
              <Button variant="ghost" size="sm" className="icon-action" title={t(item.enabled ? "Disable before deleting" : "Delete {name}", { name: item.name })} aria-label={t("Delete {name}", { name: item.name })} disabled={busy || item.enabled} onClick={() => { setRemove(item); setHistory(null); setDraft(null); }}><Trash2 size={16} aria-hidden="true" /></Button>
            </div>
          </div>
        </article>
      ))}
      {remove && <div className="rounded-lg border p-4 space-y-3" role="group" aria-label={t("Confirm deletion")}>
        <p className="text-sm">{t("Delete {name}? Historical versions will remain available.", { name: remove.name })}</p>
        <div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={() => action(async () => { await send(`/library/${kind}/${remove.slug}?expected_version=${remove.version}`, undefined, "DELETE"); setRemove(null); }, "Definition deleted. Historical versions retained.")}>{t("Confirm deletion")}</Button><Button variant="outline" disabled={busy} onClick={() => setRemove(null)}>{t("Cancel")}</Button></div>
      </div>}
      {draft && <form className="rounded-lg border p-4" onSubmit={event => {
        event.preventDefault();
        const submitted = { ...draft };
        action(async () => {
          await send(`/library/${kind}${editing ? `/${editing}` : ""}`, submitted, editing ? "PUT" : "POST");
          setDraft(null); setEditing(null);
        }, "Library definition saved.");
      }}>
        <h3>{t(editing ? "Edit definition" : kind === "agent" ? "New agent" : "New skill")}</h3>
        <fieldset disabled={busy} className="min-w-0">
          <div className="field"><label htmlFor={`${prefix}-slug`}>{t("Identifier")}</label><Input id={`${prefix}-slug`} required disabled={!!editing} maxLength={50} pattern="[a-z0-9]+(-[a-z0-9]+)*" value={draft.slug} onChange={event => setDraft({ ...draft, slug: event.target.value })} /><p className="mt-1 text-xs muted">{t("Lowercase letters, numbers and hyphens. The identifier stays unchanged after creation.")}</p></div>
          <div className="field"><label htmlFor={`${prefix}-name`}>{t("Name")}</label><Input id={`${prefix}-name`} required maxLength={100} value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} /></div>
          <div className="field"><label htmlFor={`${prefix}-objective`}>{t("Objective")}</label><textarea id={`${prefix}-objective`} className="w-full rounded-md border bg-background p-3 text-sm" required maxLength={4000} rows={3} value={draft.objective} onChange={event => setDraft({ ...draft, objective: event.target.value })} /></div>
          <div className="field"><label htmlFor={`${prefix}-instructions`}>{t("Instructions")}</label><textarea id={`${prefix}-instructions`} className="w-full rounded-md border bg-background p-3 text-sm" required maxLength={12000} rows={7} value={draft.instructions} onChange={event => setDraft({ ...draft, instructions: event.target.value })} /></div>
          <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.enabled} onChange={event => setDraft({ ...draft, enabled: event.target.checked })} />{t("Active")}</label>
          <fieldset className="mt-5 min-w-0"><legend className="text-sm font-medium">{t("Compatible assistants")}</legend><p className="mt-1 text-xs muted">{t("Leave both unchecked for all supported assistants.")}</p><div className="mt-2 flex flex-wrap gap-4">{[["codex", "ChatGPT / Codex"], ["claude", "Claude Code"]].map(([value, label]) => <label key={value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.compatibility.includes(value)} onChange={() => setDraft({ ...draft, compatibility: toggle(draft.compatibility, value) })} />{label}</label>)}</div></fieldset>
          <fieldset className="mt-5 min-w-0"><legend className="text-sm font-medium">{t("Required capabilities")}</legend><p className="mt-1 text-xs muted">{t("Requirements check compatibility; they do not grant permissions.")}</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{capabilities.map(([value, label]) => <label key={value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.required_capabilities.includes(value)} onChange={() => setDraft({ ...draft, required_capabilities: toggle(draft.required_capabilities, value) })} />{t(label)}</label>)}</div></fieldset>
          {kind === "agent" && <fieldset className="mt-5 min-w-0"><legend className="text-sm font-medium">{t("Required skills")}</legend><div className="mt-2 grid gap-2 sm:grid-cols-2">{skills.filter(item => item.enabled || draft.skills?.includes(item.slug)).map(skill => <label key={skill.slug} className="flex items-start gap-2 text-sm"><input type="checkbox" checked={draft.skills?.includes(skill.slug) || false} onChange={() => setDraft({ ...draft, skills: toggle(draft.skills || [], skill.slug) })} /><span>{skill.name}{!skill.enabled ? ` · ${t("Inactive")}` : ""}</span></label>)}</div></fieldset>}
          {editing && <p className="mt-5 text-xs muted">{t("Editing version {version}. Saving creates a new immutable version.", { version: draft.expected_version || 1 })}</p>}
          <div className="mt-5 flex flex-wrap gap-2"><Button disabled={busy}>{t("Save definition")}</Button><Button type="button" variant="outline" disabled={busy} onClick={() => { setDraft(null); setEditing(null); }}>{t("Cancel")}</Button></div>
        </fieldset>
      </form>}
      {history && <div className="rounded-lg border p-4 space-y-4">
        <h3>{t("Versions of {name}", { name: history.name })}</h3>
        {history.rows.map(row => <details key={row.version} className="rounded-md border p-3"><summary className="cursor-pointer text-sm">v{row.version} · {t(({ created: "Created", edited: "Edited", deleted: "Deleted", imported: "Imported" } as Record<string, string>)[row.action] || row.action)} · {t("Editor")}: {row.editor} · {new Date(row.created_at).toLocaleString(dateLocale)}</summary><div className="mt-3 text-sm space-y-2"><p>{row.definition.objective}</p><pre className="whitespace-pre-wrap break-words font-sans">{row.definition.instructions}</pre></div></details>)}
        <Button variant="outline" size="sm" onClick={() => setHistory(null)}>{t("Close")}</Button>
      </div>}
    </Card>
  );
}
