"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { LibraryDefinition } from "@/components/ai-library";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Selection = { revision: number; agents: string[] | null; skills: string[] | null };
type Connection = { id: number; name: string; agent: string; model: string; enabled: boolean };
type Preview = {
  compatible: boolean;
  incompatibilities: { slug: string; kind: string; reason: string; missing_capabilities?: string[] }[];
  instructions: string;
  provider: string;
  library: { agents: LibraryDefinition[]; skills: LibraryDefinition[] };
};
export function EnvironmentLibrary({ environmentId }: { environmentId: number }) {
  const { t } = useI18n();
  const [selection, setSelection] = useState<Selection | null>(null);
  const [agents, setAgents] = useState<LibraryDefinition[]>([]);
  const [skills, setSkills] = useState<LibraryDefinition[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [opened, setOpened] = useState(false);
  const generation = useRef(0);
  const prefix = `environment-${environmentId}-library`;
  async function load() {
    const version = ++generation.current;
    const [value, availableAgents, availableSkills, ais] = await Promise.all([
      api<Selection>(`/environments/${environmentId}/library`),
      api<LibraryDefinition[]>("/library/agent"),
      api<LibraryDefinition[]>("/library/skill"),
      api<Connection[]>("/ai-connections"),
    ]);
    if (version !== generation.current) return;
    setSelection(value); setAgents(availableAgents); setSkills(availableSkills);
    setConnections(ais); setPreview(null);
  }
  useEffect(() => {
    if (!opened) return;
    load().catch(error => setError(error.message));
    return () => { generation.current += 1; };
  }, [environmentId, opened]);
  function update(changes: Partial<Selection>) {
    setSelection(value => value ? { ...value, ...changes } : value);
    setPreview(null); setNotice(""); setError("");
  }
  const payload = selection && { expected_revision: selection.revision, agents: selection.agents, skills: selection.skills };
  return (
    <details className="mt-5 rounded-lg border p-4" onToggle={event => setOpened(event.currentTarget.open)}>
      <summary className="cursor-pointer text-sm font-medium"><BookOpen size={16} className="mr-2 inline-block" aria-hidden="true" />{t("Agents and skills for this environment")}</summary>
      {opened && <div className="mt-4 space-y-4">
        <p className="text-sm muted">{t("Choose references from the shared library. Definitions are not copied into this environment.")}</p>
        {error && <div role="alert" className="rounded-md border p-3 text-sm">{t(error)} <Button variant="ghost" size="sm" disabled={busy} onClick={() => { setError(""); load().catch(error => setError(error.message)); }}>{t("Reload configuration")}</Button></div>}
        {!selection && !error && <p role="status" className="text-sm muted">{t("Loading library…")}</p>}
        {notice && <p role="status" className="text-sm">{t(notice)}</p>}
        {selection && <fieldset disabled={busy} className="min-w-0">
          {([["agents", agents, "Agents"], ["skills", skills, "Skills"]] as const).map(([key, available, label]) => <fieldset className="mb-5 min-w-0" key={key}>
            <legend className="text-sm font-medium">{t(label)}</legend>
            <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={selection[key] === null} onChange={event => update({ [key]: event.target.checked ? null : available.filter(item => item.enabled).map(item => item.slug) })} />{t("Inherit all active definitions")}</label>
            {selection[key] !== null && <div className="mt-3 grid gap-2 sm:grid-cols-2">{available.filter(item => item.enabled || selection[key]?.includes(item.slug)).map(item => <label key={item.slug} className="flex items-start gap-2 text-sm"><input type="checkbox" checked={selection[key]?.includes(item.slug) || false} onChange={event => update({ [key]: event.target.checked ? [...selection[key]!, item.slug] : selection[key]!.filter(slug => slug !== item.slug) })} /><span>{item.name} <span className="text-xs muted">v{item.version}{!item.enabled ? ` · ${t("Inactive")}` : ""}</span></span></label>)}</div>}
          </fieldset>)}
          <div className="field"><label htmlFor={`${prefix}-connection`}>{t("Preview with an AI connection")}</label><select id={`${prefix}-connection`} value={connectionId} onChange={event => { setConnectionId(event.target.value); setPreview(null); setNotice(""); }}><option value="">{t("Select an AI connection")}</option>{connections.filter(item => item.enabled).map(item => <option key={item.id} value={item.id}>{item.name} · {item.agent === "codex" ? "ChatGPT / Codex" : "Claude Code"} · {item.model || t("Provider default model")}</option>)}</select></div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="button" variant="outline" className="h-auto min-h-10 max-w-full whitespace-normal" disabled={busy || !connectionId} onClick={async () => {
              setBusy(true); setError(""); setNotice(""); setPreview(null);
              try { setPreview(await send<Preview>(`/environments/${environmentId}/library/preview?connection_id=${connectionId}`, payload)); }
              catch (error) { setError((error as Error).message); }
              finally { setBusy(false); }
            }}><Eye size={16} aria-hidden="true" />{t("Preview effective configuration")}</Button>
            <Button type="button" className="h-auto min-h-10 max-w-full whitespace-normal" disabled={busy || !preview?.compatible} onClick={async () => {
              setBusy(true); setError(""); setNotice("");
              try {
                const saved = await send<Selection>(`/environments/${environmentId}/library`, payload, "PUT");
                setSelection(saved); setPreview(null); setNotice("Environment library selection saved.");
              } catch (error) { setError((error as Error).message); }
              finally { setBusy(false); }
            }}>{t("Save environment selection")}</Button>
          </div>
          <p className="mt-2 text-xs muted">{t("Preview the current selection with an assistant before saving. Existing analyses retain their frozen definitions.")}</p>
        </fieldset>}
        {preview && <div className="rounded-md border p-4 space-y-3" role="status">
          <h4 className="text-sm font-medium">{t(preview.compatible ? "Compatible configuration" : "Configuration needs attention")}</h4>
          {!preview.compatible && <ul className="list-disc space-y-1 pl-5 text-sm">{preview.incompatibilities.map((item, index) => <li key={`${item.slug}-${index}`}><strong>{item.slug}</strong>: {t(item.reason)}{item.missing_capabilities?.length ? ` (${item.missing_capabilities.map(value => t(({ read_sources: "Read project sources", read_attachments: "Read attachments", read_database: "Read the business database", structured_output: "Produce structured results" } as Record<string, string>)[value] || value)).join(", ")})` : ""}</li>)}</ul>}
          <p className="text-xs muted">{t("Provider")}: {preview.provider === "codex" ? "ChatGPT / Codex" : "Claude Code"} · {t("Agents")}: {preview.library.agents.length} · {t("Skills")}: {preview.library.skills.length}</p>
          <details><summary className="cursor-pointer text-sm">{t("Effective instructions")}</summary><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs font-sans">{preview.instructions}</pre></details>
        </div>}
      </div>}
    </details>
  );
}
