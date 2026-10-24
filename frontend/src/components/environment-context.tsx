"use client";

import { useRef, useState } from "react";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type Resource = {
  id: string; name: string; enabled: boolean; filename: string;
  content_type: string; size: number; sha256: string; version: number;
  version_id: string; updated_at: string; preview: string;
  preview_truncated?: boolean; agent_readable: boolean;
};
type Configuration = {
  instructions: string; instructions_enabled: boolean; revision: number;
  max_files: number; max_file_size: number; resources: Resource[];
  official_references?: { url: string; note: string }[];
};

export function EnvironmentContext({ environmentId, factualOnly = false }: { environmentId: number; factualOnly?: boolean }) {
  const { t, dateLocale } = useI18n();
  const [value, setValue] = useState<Configuration | null>(null);
  const [instructions, setInstructions] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [references, setReferences] = useState<{ url: string; note: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const upload = useRef<HTMLInputElement>(null);
  const endpoint = `/environments/${environmentId}/context`;
  function receive(next: Configuration) {
    setValue(next);
    setInstructions(next.instructions);
    setEnabled(next.instructions_enabled);
    setReferences(next.official_references || []);
  }
  async function task(action: () => Promise<Configuration>, saved = true) {
    setBusy(true); setError(""); setNotice("");
    try { receive(await action()); if (saved) setNotice(t("Environment context saved. Existing analyses remain unchanged.")); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function fileChange(file: File | undefined, resource?: Resource) {
    if (!file || !value) return;
    if (file.size > value.max_file_size) { setError(t("This file exceeds the environment context size limit.")); return; }
    const data = new FormData();
    data.set("file", file); data.set("expected_revision", String(value.revision));
    await task(() => api<Configuration>(`${endpoint}/resources${resource ? `/${resource.id}/versions` : ""}`, { method: "POST", body: data }));
    if (upload.current) upload.current.value = "";
  }
  const dirty = !!value && (instructions !== value.instructions || enabled !== value.instructions_enabled || JSON.stringify(references) !== JSON.stringify(value.official_references || []));
  function toggleResource(resource: Resource, nextEnabled: boolean) {
    if (!value) return;
    const previous = value;
    setValue({ ...value, resources: value.resources.map(item => item.id === resource.id ? { ...item, enabled: nextEnabled } : item) });
    void task(async () => {
      try { return await send<Configuration>(`${endpoint}/resources/${resource.id}`, { enabled: nextEnabled, expected_revision: previous.revision }, "PATCH"); }
      catch (error) { setValue(previous); throw error; }
    });
  }
  return <details className="mt-5 rounded-lg border p-4" onToggle={(event) => {
    if (event.currentTarget.open && !value && !busy) void task(() => api<Configuration>(endpoint), false);
  }}>
    <summary className="cursor-pointer font-medium">{t("Environment context")}</summary>
    <p className="mt-3 text-sm muted">{t(factualOnly ? "Reference documents, business terminology and factual context for this environment. These are source data, not instructions for the assistants." : "Optional shared reference documents and short instructions for this environment. Request attachments remain separate.")}</p>
    {error && <p role="alert" className="mt-3 text-sm text-red-700">{t(error)} <Button variant="ghost" size="sm" disabled={busy} onClick={() => task(() => api<Configuration>(endpoint), false)}>{t("Reload context")}</Button></p>}
    {notice && <p role="status" className="mt-3 text-sm text-green-700">{notice}</p>}
    {!value ? <p role="status" className="mt-3 text-sm">{t("Loading context…")}</p> : <fieldset disabled={busy} className="min-w-0 space-y-4">
      <form onSubmit={(event) => { event.preventDefault(); void task(() => send<Configuration>(endpoint, { instructions, instructions_enabled: enabled, official_references: references, expected_revision: value.revision }, "PUT")); }}>
        <div className="field">
          <label htmlFor={`context-instructions-${environmentId}`}>{t(factualOnly ? "Business terminology and factual context" : "Short environment instructions")}</label>
          <Textarea id={`context-instructions-${environmentId}`} value={instructions} maxLength={4000} onChange={(event) => setInstructions(event.target.value)} aria-describedby={`context-secret-note-${environmentId}`} />
          <p id={`context-secret-note-${environmentId}`} className="mt-2 text-xs muted">{t("Keep credentials in the secure Git and database configuration. Never enter passwords or tokens here.")}</p>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />{t(factualOnly ? "Use business context" : "Use environment instructions")}</label>
        <section className="mt-4 space-y-3" aria-label={t("Official reference sources")}>
          <h4 className="text-sm font-medium">{t("Official reference sources")}</h4>
          <p className="text-xs muted">{t("Optional public URLs or domains and applicability notes. These are starting points, not an exclusive list or assistant instructions.")}</p>
          {references.map((reference, index) => <div key={index} className="min-w-0 space-y-2 rounded border p-3">
            <label className="block text-sm" htmlFor={`reference-url-${environmentId}-${index}`}>{t("Reference URL or domain")}</label>
            <Input id={`reference-url-${environmentId}-${index}`} value={reference.url} required maxLength={2048} onChange={event => setReferences(references.map((row, i) => i === index ? { ...row, url: event.target.value } : row))} />
            <label className="block text-sm" htmlFor={`reference-note-${environmentId}-${index}`}>{t("Reference note")}</label>
            <Textarea id={`reference-note-${environmentId}-${index}`} value={reference.note} maxLength={1000} onChange={event => setReferences(references.map((row, i) => i === index ? { ...row, note: event.target.value } : row))} />
            <Button type="button" variant="ghost" size="sm" onClick={() => setReferences(references.filter((_, i) => i !== index))}>{t("Remove reference {number}", { number: index + 1 })}</Button>
          </div>)}
          <Button type="button" variant="outline" size="sm" disabled={references.length >= 12} onClick={() => setReferences([...references, { url: "", note: "" }])}>{t("Add official reference")}</Button>
        </section>
        <div className="mt-3 flex flex-wrap gap-2"><Button className="h-auto min-h-10 max-w-full whitespace-normal" disabled={busy || !dirty}>{t(factualOnly ? "Save business context" : "Save context instructions")}</Button>{dirty && !error && <Button type="button" variant="outline" disabled={busy} onClick={() => task(() => api<Configuration>(endpoint), false)}>{t("Reload context")}</Button>}</div>
      </form>
      <div className="rounded-lg bg-muted p-3 text-sm">
        <p>{t("Up to {count} documents, {size} MB each.", { count: value.max_files, size: Math.round(value.max_file_size / 1048576) })}</p>
        <p className="mt-1 muted">{t("Documents are available on demand; they are not all copied into the initial prompt.")}</p>
        {dirty && <p className="mt-2 text-amber-800">{t(factualOnly ? "Save or reload your business context before changing documents." : "Save or reload your instruction changes before changing documents.")}</p>}
        <label className="mt-3 block font-medium" htmlFor={`context-upload-${environmentId}`}>{t("Add reference document")}</label>
        <Input ref={upload} id={`context-upload-${environmentId}`} type="file" className="mt-2" disabled={busy || dirty || value.resources.length >= value.max_files} onChange={(event) => void fileChange(event.target.files?.[0])} />
      </div>
      {!value.resources.length && <p className="text-sm muted">{t("No environment reference documents.")}</p>}
      <ul className="space-y-4">
        {value.resources.map((resource) => <li key={resource.id} className="min-w-0 rounded-lg border p-4">
          <p className="break-words font-medium">{resource.name}</p>
          <p className="mt-1 break-words text-xs muted">{resource.filename} · {resource.content_type} · {resource.size.toLocaleString(dateLocale)} {t("bytes")} · {t("Version")} {resource.version} · {new Date(resource.updated_at).toLocaleString(dateLocale)}</p>
          <p className="mt-1 break-all text-xs muted">SHA-256: <code>{resource.sha256}</code></p>
          <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={resource.enabled} disabled={busy || dirty} onChange={(event) => toggleResource(resource, event.target.checked)} />{t("Use {name}", { name: resource.name })}</label>
          {!resource.agent_readable ? <p className="mt-2 text-sm text-amber-800">{t("This format is not readable by the agent. Replace it with a supported document.")}</p> : resource.preview ? <details className="mt-3 text-sm"><summary className="cursor-pointer">{t("Text preview")}</summary><pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-3 font-sans">{resource.preview}</pre>{resource.preview_truncated && <p className="mt-2 muted">{t("Preview shortened. The agent can read the complete file on demand.")}</p>}</details> : <p className="mt-2 text-sm muted">{t("No text preview. The agent can inspect this supported format on demand.")}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
            <a className="text-primary underline" href={`/api${endpoint}/resources/${resource.id}/versions/${resource.version_id}/download`}>{t("Download document")}</a>
            <label className="text-primary underline">{t("Replace {name}", { name: resource.name })}<input aria-label={t("Replace {name}", { name: resource.name })} type="file" className="mt-1 block max-w-full text-xs" disabled={busy || dirty} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void fileChange(file, resource); }} /></label>
            <Button variant="ghost" size="sm" disabled={busy || dirty} onClick={() => { if (window.confirm(t("Remove this reference document? Existing analyses retain their frozen version."))) void task(() => api<Configuration>(`${endpoint}/resources/${resource.id}?expected_revision=${value.revision}`, { method: "DELETE" })); }}>{t("Remove {name}", { name: resource.name })}</Button>
          </div>
        </li>)}
      </ul>
    </fieldset>}
  </details>;
}
