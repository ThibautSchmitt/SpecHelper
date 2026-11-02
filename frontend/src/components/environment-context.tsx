"use client";

import { useRef, useState, type ReactNode } from "react";
import { ChevronDown, Download, FileText, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type Reference = { url: string; note: string };
type Resource = {
  id: string; name: string; enabled: boolean; filename: string;
  content_type: string; size: number; sha256: string; version: number;
  version_id: string; updated_at: string; preview?: string | null;
  preview_truncated?: boolean; agent_readable: boolean;
};
export type KnowledgeDraft = {
  instructions: string; references: Reference[]; files: File[];
  linkEditor?: { index: number | null; url: string; note: string };
};
export const emptyKnowledge = (): KnowledgeDraft => ({ instructions: "", references: [], files: [] });
type Configuration = {
  instructions: string; revision: number; max_files: number; max_file_size: number;
  resources: Resource[]; official_references?: Reference[];
};
type Summary = { has_text: boolean; documents: number; sites: number };

function referenceHref(value: string) {
  try {
    const url = new URL(value.includes("://") ? value : "https://" + value);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}

/** One compact editor reused by new and existing environments. It never submits its own form. */
export function KnowledgePanel({ id, draft, onChange, resources = [], endpoint, maxFiles = 20,
  maxSize = 25 * 1048576, busy = false, readOnlyText = false, loaded = true, summary,
  onOpen, onUpload, onToggle, onRemove, onError, children,
}: {
  id: string; draft: KnowledgeDraft; onChange: (draft: KnowledgeDraft) => void;
  resources?: Resource[]; endpoint?: string; maxFiles?: number; maxSize?: number;
  busy?: boolean; readOnlyText?: boolean; loaded?: boolean; summary?: Summary;
  onOpen?: () => void; onUpload?: (file: File, resource?: Resource) => Promise<void>;
  onToggle?: (resource: Resource, enabled: boolean) => void; onRemove?: (resource: Resource) => void;
  onError: (message: string) => void; children?: ReactNode;
}) {
  const { t, dateLocale } = useI18n();
  const upload = useRef<HTMLInputElement>(null);
  const replacing = useRef<Resource | undefined>(undefined);
  const urlInput = useRef<HTMLInputElement>(null);
  const count = loaded ? resources.length + draft.files.length : summary?.documents || 0;
  const sites = loaded ? draft.references.length : summary?.sites || 0;
  const hasText = loaded ? !!draft.instructions.trim() : !!summary?.has_text;
  const parts = [
    hasText ? t("Business context provided") : "",
    count ? t(count === 1 ? "1 document" : "{count} documents", { count }) : "",
    sites ? t(sites === 1 ? "1 link" : "{count} links", { count: sites }) : "",
  ].filter(Boolean);
  const link = draft.linkEditor;
  function update(patch: Partial<KnowledgeDraft>) { onChange({ ...draft, ...patch }); }
  function editLink(index: number | null) {
    update({ linkEditor: index === null ? { index, url: "", note: "" } : { index, ...draft.references[index] } });
  }
  function acceptLink() {
    if (!link) return;
    if (!link.url.trim()) { urlInput.current?.setCustomValidity(t("Enter a reference URL or domain.")); urlInput.current?.reportValidity(); return; }
    const references = [...draft.references];
    const value = { url: link.url.trim(), note: link.note };
    if (link.index === null) references.push(value); else references[link.index] = value;
    update({ references, linkEditor: undefined });
  }
  async function choose(file?: File) {
    if (!file) return;
    const target = replacing.current;
    replacing.current = undefined;
    if (file.size > maxSize) { onError(t("This file exceeds the environment context size limit.")); return; }
    if (!target && count >= maxFiles) { onError(t("A maximum of 20 context resources is allowed.")); return; }
    if (onUpload) await onUpload(file, target);
    else update({ files: [...draft.files, file] });
  }
  function size(bytes: number) {
    if (bytes < 1024) return bytes.toLocaleString(dateLocale) + " " + t("bytes");
    return t("{size} KB", { size: new Intl.NumberFormat(dateLocale, { maximumFractionDigits: 1 }).format(bytes / 1024) });
  }
  return <details className="application-knowledge mt-5 min-w-0 rounded-lg border p-4"
    onToggle={event => { if (event.currentTarget.open && event.target === event.currentTarget) onOpen?.(); }}>
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
      <span className="min-w-0"><span className="block text-sm font-medium">{t("Application knowledge")}</span>
        <span className="mt-1 block text-xs muted">{parts.length ? parts.join(" · ") : t("Optional · Add useful context, documents or links.")}</span>
      </span><ChevronDown size={15} className="shrink-0" aria-hidden="true" />
    </summary>
    <p className="mt-4 text-sm muted">{t("Help the AI understand this environment’s vocabulary, business specifics and references.")}</p>
    {!loaded ? <>{children}</> : <>
      <fieldset disabled={busy} className="mt-4 min-w-0 space-y-6">
        <div className="field">
          <label htmlFor={id + "-presentation"}>{t("Business presentation and vocabulary")}</label>
          <Textarea id={id + "-presentation"} rows={4} className="min-h-0 resize-y" value={draft.instructions}
            disabled={readOnlyText} maxLength={4000}
            placeholder={t("E.g. The application manages insurance claims. An ancillary benefit means…")}
            aria-describedby={id + "-help"} onChange={event => update({ instructions: event.target.value })} />
          <p id={id + "-help"} className="mt-2 text-xs muted">{t("Optional · Describe business specifics that are not obvious from the code.")}</p>
        </div>
        <section className="min-w-0" aria-label={t("Reference documents")}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0"><h4 className="text-sm font-medium">{t("Reference documents")}</h4>
              <p className="mt-1 text-xs muted">{t("Specifications, procedures and business documentation useful for analyses.")}</p></div>
            <Button type="button" size="sm" variant="outline" disabled={busy || count >= maxFiles || readOnlyText && !onUpload}
              onClick={() => { replacing.current = undefined; upload.current?.click(); }}>
              <Plus size={15} aria-hidden="true" />{t("Add a document")}
            </Button>
          </div>
          <input ref={upload} type="file" hidden aria-label={t("Add a document")} data-knowledge-upload
            onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; void choose(file); }} />
          <p className="mt-2 text-xs muted">{t("Up to {count} documents, {size} MB each.", { count: maxFiles, size: Math.round(maxSize / 1048576) })}</p>
          {!count && <p className="mt-3 text-sm muted">{t("No documents added.")}</p>}
          <ul className="mt-3 min-w-0 space-y-3">{resources.map(resource => <li key={resource.id} className="min-w-0 text-sm" data-document-id={resource.id}>
            <div className="flex min-w-0 items-start gap-2">
              <FileText size={16} className="mt-1 shrink-0 muted" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <a className="break-all text-primary underline" href={"/api" + endpoint + "/resources/" + resource.id + "/versions/" + resource.version_id + "/download"}>{resource.filename}</a>
                <p className="mt-1 text-xs muted">{size(resource.size)}{!resource.enabled && " · " + t("Disabled")}</p>
                {!resource.agent_readable && <p className="mt-1 text-xs muted">{t("Unreadable document. Replace it with a supported file.")}</p>}
              </div>
              <details className="action-menu shrink-0" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
                <summary aria-label={t("More actions for {name}", { name: resource.filename })}>⋯</summary>
                <div className="action-menu-items" onClick={event => { if (event.target instanceof Element && event.target.closest("button")) { const menu = event.currentTarget.closest("details"); if (menu) menu.open = false; } }}>
                  <Button type="button" size="sm" variant="ghost" onClick={() => { replacing.current = resource; upload.current?.click(); }}><RefreshCw size={15} aria-hidden="true" />{t("Replace {name}", { name: resource.filename })}</Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => onRemove?.(resource)}><Trash2 size={15} aria-hidden="true" />{t("Remove {name}", { name: resource.filename })}</Button>
                </div>
              </details>
            </div>
            <details className="mt-2 pl-6 text-xs">
              <summary className="cursor-pointer muted">{t("Document details")}</summary>
              <p className="mt-2 break-words muted">{resource.content_type} · {t("Version")} {resource.version} · {new Date(resource.updated_at).toLocaleString(dateLocale)}</p>
              <p className="mt-2 break-all muted">SHA-256: <code>{resource.sha256}</code></p>
              <label className="mt-3 flex items-center gap-2"><input type="checkbox" checked={resource.enabled}
                onChange={event => onToggle?.(resource, event.target.checked)} />{t("Use {name}", { name: resource.name })}</label>
              {!resource.agent_readable ? <p className="mt-2">{t("This format is not readable by the agent. Replace it with a supported document.")}</p> :
                resource.preview ? <details className="mt-2"><summary className="cursor-pointer">{t("Text preview")}</summary>
                  <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-3 font-sans">{resource.preview}</pre>
                  {resource.preview_truncated && <p className="mt-2 muted">{t("Preview shortened. The agent can read the complete file on demand.")}</p>}</details> : null}
              <a className="mt-2 inline-flex items-center gap-1 text-primary underline" href={"/api" + endpoint + "/resources/" + resource.id + "/versions/" + resource.version_id + "/download"}><Download size={12} aria-hidden="true" />{t("Download document")}</a>
            </details>
          </li>)}
          {draft.files.map((file, index) => <li key={index} className="flex min-w-0 items-start gap-2 text-sm">
            <FileText size={16} className="mt-1 shrink-0 muted" aria-hidden="true" />
            <div className="min-w-0 flex-1"><p className="break-all">{file.name}</p><p className="mt-1 text-xs muted">{size(file.size)}</p></div>
            <Button type="button" size="sm" variant="ghost" aria-label={t("Remove {name}", { name: file.name })} onClick={() => update({ files: draft.files.filter((_, i) => i !== index) })}><Trash2 size={15} aria-hidden="true" /></Button>
          </li>)}</ul>
        </section>
        <section className="min-w-0" aria-label={t("Reference sites")}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h4 className="text-sm font-medium">{t("Reference sites")}</h4>
              <p className="mt-1 text-xs muted">{t("Add links to useful documentation or sources.")}</p></div>
            <Button type="button" size="sm" variant="outline" disabled={readOnlyText || draft.references.length >= 12 || !!link}
              onClick={() => editLink(null)}><Plus size={15} aria-hidden="true" />{t("Add a link")}</Button>
          </div>
          {!draft.references.length && !link && <p className="mt-3 text-sm muted">{t("No sites added.")}</p>}
          <ul className="mt-3 space-y-3">{draft.references.map((reference, index) => <li key={index} className="flex min-w-0 items-start gap-2 text-sm">
            <div className="min-w-0 flex-1">
              <a className="break-all text-primary underline" href={referenceHref(reference.url)} target="_blank" rel="noopener noreferrer">{reference.url}</a>
              {reference.note && <p className="mt-1 whitespace-pre-wrap break-words text-xs muted">{reference.note}</p>}
            </div>
            <Button type="button" variant="ghost" size="sm" disabled={readOnlyText || !!link} aria-label={t("Edit link {number}", { number: index + 1 })} onClick={() => editLink(index)}><Pencil size={14} aria-hidden="true" /></Button>
            <Button type="button" variant="ghost" size="sm" disabled={readOnlyText || !!link} aria-label={t("Remove reference {number}", { number: index + 1 })} onClick={() => update({ references: draft.references.filter((_, i) => i !== index) })}><Trash2 size={14} aria-hidden="true" /></Button>
          </li>)}</ul>
          {link && <div role="group" aria-label={t(link.index === null ? "Add a link" : "Edit reference link")} className="mt-3 space-y-3">
            <div className="field"><label htmlFor={id + "-url"}>{t("Reference URL or domain")}</label>
              <Input ref={urlInput} id={id + "-url"} value={link.url} maxLength={2048} autoFocus
                onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); acceptLink(); } }}
                onChange={event => { event.target.setCustomValidity(""); update({ linkEditor: { ...link, url: event.target.value } }); }} />
            </div>
            <div className="field"><label htmlFor={id + "-note"}>{t("Applicability note (optional)")}</label>
              <Textarea id={id + "-note"} rows={2} className="min-h-0 resize-y" value={link.note} maxLength={1000}
                onChange={event => update({ linkEditor: { ...link, note: event.target.value } })} />
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <Button type="button" size="sm" variant="outline" onClick={() => update({ linkEditor: undefined })}>{t("Cancel")}</Button>
              <Button type="button" size="sm" onClick={acceptLink}>{t(link.index === null ? "Add" : "Save")}</Button>
            </div>
          </div>}
        </section>
      </fieldset>
      {children}
    </>}
  </details>;
}

export function EnvironmentContext({ environmentId, summary }: {
  environmentId: number; summary?: Summary;
}) {
  const { t } = useI18n();
  const [value, setValue] = useState<Configuration | null>(null);
  const [draft, setDraft] = useState<KnowledgeDraft>(emptyKnowledge);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const endpoint = "/environments/" + environmentId + "/context";
  const dirty = !!value && (!!draft.linkEditor || draft.instructions !== value.instructions || JSON.stringify(draft.references) !== JSON.stringify(value.official_references || []));
  function change(next: KnowledgeDraft) { setDraft(next); setNotice(""); }
  async function task(action: () => Promise<Configuration>, mode: "load" | "save" | "documents") {
    setBusy(true); setError(""); setNotice("");
    try {
      const next = await action();
      const nextDraft = mode === "documents" ? draft : { ...emptyKnowledge(), instructions: next.instructions, references: next.official_references || [] };
      setValue(next); setDraft(nextDraft);
      if (mode !== "load") setNotice(mode === "documents" ? t("Documents updated.") + (dirty ? " " + t("Text and link changes still need saving.") : "") : t("Application knowledge saved."));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function reload() {
    if (dirty && !window.confirm(t("Discard unsaved knowledge changes and reload?"))) return;
    void task(() => api<Configuration>(endpoint), "load");
  }
  function remove(resource: Resource) {
    if (value && window.confirm(t("Remove this reference document? Existing analyses retain their frozen version.")))
      void task(() => api<Configuration>(endpoint + "/resources/" + resource.id + "?expected_revision=" + value.revision, { method: "DELETE" }), "documents");
  }
  return <form className="min-w-0" aria-busy={busy} onSubmit={event => {
    event.preventDefault();
    if (value && dirty && !draft.linkEditor && !busy) void task(() => send<Configuration>(endpoint, {
      instructions: draft.instructions, official_references: draft.references, expected_revision: value.revision,
    }, "PUT"), "save");
  }}>
    <KnowledgePanel id={"knowledge-" + environmentId} draft={draft} onChange={change} summary={summary}
      resources={value?.resources} endpoint={endpoint} maxFiles={value?.max_files} maxSize={value?.max_file_size}
      busy={busy} loaded={!!value} onOpen={() => { if (!busy && (!value || !dirty)) void task(() => api<Configuration>(endpoint), "load"); }}
      onError={message => { setError(message); setNotice(""); }}
      onUpload={async (file, resource) => {
        if (!value) return;
        const data = new FormData(); data.set("file", file); data.set("expected_revision", String(value.revision));
        await task(() => api<Configuration>(endpoint + "/resources" + (resource ? "/" + resource.id + "/versions" : ""), { method: "POST", body: data }), "documents");
      }}
      onToggle={(resource, enabled) => { if (value) void task(() => send<Configuration>(endpoint + "/resources/" + resource.id, { enabled, expected_revision: value.revision }, "PATCH"), "documents"); }}
      onRemove={remove}>
      {error && <p role="alert" className="mt-4 text-sm text-red-700">{t(error)} <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={reload}>{t("Reload context")}</Button></p>}
      {!value && !error && <p role="status" className="mt-4 text-sm muted">{t("Loading context…")}</p>}
      {notice && <p role="status" className="mt-4 text-sm text-green-700">{notice}</p>}
      {value && <div className="mt-4 flex justify-end gap-2">
        <Button disabled={busy || !dirty || !!draft.linkEditor}>{t("Save")}</Button>
      </div>}
    </KnowledgePanel>
  </form>;
}

/** Retry only pending uploads against the already-created environment. */
export async function uploadCreationDocuments(environmentId: number, files: File[], onUploaded: (file: File) => void) {
  const endpoint = "/environments/" + environmentId + "/context";
  let current = await api<Configuration>(endpoint);
  for (const file of files) {
    let alreadyStored = false;
    if (globalThis.crypto?.subtle) {
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()))).map(byte => byte.toString(16).padStart(2, "0")).join("");
      alreadyStored = current.resources.some(resource => resource.filename === file.name && resource.size === file.size && resource.sha256 === hash);
    }
    if (!alreadyStored) {
      const body = new FormData(); body.set("file", file); body.set("expected_revision", String(current.revision));
      current = await api<Configuration>(endpoint + "/resources", { method: "POST", body });
    }
    onUploaded(file);
  }
}
