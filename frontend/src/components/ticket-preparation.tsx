"use client";

import { useRef, useState } from "react";
import { FileText } from "lucide-react";
import { api, send, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PublishTicket } from "@/components/publish-ticket";

type Draft = {
  revision: number; discussion_revision: number;
  source_version: number | null; source_verified: boolean;
  analysis_state: "none" | "complete" | "partial" | "interrupted" | "in_progress";
  verified_scope: string; limitations: string[]; has_new_messages: boolean;
  scope_choice: "unknown" | "covered" | "clarified" | "changed";
  update_recommended: boolean; title: string; body: string; markdown: string;
  publication_available: boolean; publication_allowed: boolean;
};
const states = {
  none: "No deep analysis yet.", complete: "Deep analysis completed.",
  partial: "Deep analysis has incomplete checks.", interrupted: "The last deep analysis was interrupted.",
  in_progress: "Deep analysis is in progress.",
};

export function TicketPreparation({ value, onUpdated }: { value: RequestDetail; onUpdated: (value: RequestDetail) => void }) {
  const { t } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const endpoint = `/analyses/${value.id}/ticket-preparation`;
  const working = ["QUEUED", "UNDERSTANDING", "ANALYZING", "REVIEWING", "GENERATING_RESULT", "CONTINUING_CONVERSATION", "GENERATING_TICKET", "NEEDS_CLARIFICATION"].includes(value.status);

  async function load() {
    setBusy(true); setError(""); setDraft(null); setSaved(false);
    try { setDraft(await api<Draft>(endpoint)); setDirty(false); }
    catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  function edit(changes: Partial<Draft>) {
    setDraft(current => current ? { ...current, ...changes } : current);
    setDirty(true); setSaved(false);
  }
  async function persist() {
    if (!draft) throw new Error("Load the ticket draft first.");
    if (!dirty && draft.revision) return draft;
    const updated = await send<Draft>(endpoint, {
      expected_revision: draft.revision, expected_discussion_revision: draft.discussion_revision,
      source_version: draft.source_version, scope_choice: draft.scope_choice,
      title: draft.title, body: draft.body,
    }, "PUT");
    setDraft(updated); setDirty(false); setSaved(true);
    return updated;
  }
  async function action(operation: "save" | "copy" | "download" | "analyze") {
    setBusy(true); setError("");
    try {
      const current = await persist();
      if (operation === "copy") await navigator.clipboard.writeText(current.markdown);
      if (operation === "download") {
        const url = URL.createObjectURL(new Blob([current.markdown], { type: "text/markdown;charset=utf-8" }));
        const link = document.createElement("a"); link.href = url; link.download = `ticket-${value.id}.md`;
        link.click(); URL.revokeObjectURL(url);
      }
      if (operation === "analyze") {
        const updated = await send<RequestDetail>(`/analyses/${value.id}/deep-analyze`, {
          expected_revision: current.discussion_revision, intent: "change", preparation_revision: current.revision,
        });
        onUpdated(updated); dialog.current?.close();
        window.dispatchEvent(new Event("queue-updated"));
      }
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  return <>
    <Button size="sm" variant="outline" onClick={() => { dialog.current?.showModal(); void load(); }}><FileText size={15} aria-hidden="true"/>{t("Prepare a ticket")}</Button>
    <dialog ref={dialog} className="publication-dialog" aria-labelledby={`ticket-preparation-title-${value.id}`} onCancel={event => { if (busy) event.preventDefault(); }}>
      <div className="flex items-start justify-between gap-4">
        <h2 id={`ticket-preparation-title-${value.id}`}>{t("Prepare a ticket")}</h2>
        <Button variant="ghost" disabled={busy} onClick={() => dialog.current?.close()}>{t("Cancel")}</Button>
      </div>
      <p className="mt-2 text-sm muted">{t("Preparing a draft does not launch an analysis or publish a ticket.")}</p>
      {error && <div className="mt-4" role="alert"><p>{t(error)}</p><Button variant="ghost" disabled={busy} onClick={load}>{t("Reload saved draft")}</Button></div>}
      {!draft && busy && <p className="mt-4" role="status">{t("Loading…")}</p>}
      {draft && <div className="mt-5 space-y-4">
        <div className="space-y-2 text-sm" aria-label={t("Analysis coverage")}>
          <p className="font-semibold">{t(states[draft.analysis_state])}</p>
          {draft.source_version && <p>{t("Source analysis: v{number}", { number: draft.source_version })} · {t(draft.source_verified ? "Verified findings available" : "Incomplete verification")}</p>}
          {draft.verified_scope && <details><summary className="cursor-pointer">{t("Scope studied")}</summary><p className="mt-2 whitespace-pre-wrap">{draft.verified_scope}</p></details>}
          <p>{t(draft.source_verified ? "Reuse the existing findings. Later proposals and ticket edits have not been independently verified." : "This draft is unverified: independent checks are missing or incomplete.")}</p>
          {!!draft.limitations?.length && <ul className="list-disc pl-5">{draft.limitations.map((limit, index) => <li key={index}>{limit}</li>)}</ul>}
          {draft.source_version && draft.has_new_messages && <div className="field">
            <label htmlFor="ticket-scope-choice">{t("Changes since the analysis")}</label>
            <select id="ticket-scope-choice" value={draft.scope_choice} disabled={busy} onChange={event => edit({ scope_choice: event.target.value as Draft["scope_choice"] })}>
              <option value="unknown">{t("Scope still to assess")}</option>
              <option value="covered">{t("Same need; additional discussion")}</option>
              <option value="clarified">{t("Minor clarification or proposed correction")}</option>
              <option value="changed">{t("Significant change of need")}</option>
            </select>
          </div>}
          {(draft.scope_choice === "changed" || !draft.source_verified) && <p>{t("You can update the analysis, or keep an explicitly unverified draft.")}</p>}
        </div>
        <div className="field"><label htmlFor="ticket-draft-title">{t("Ticket title")}</label><Input id="ticket-draft-title" value={draft.title} maxLength={200} disabled={busy} onChange={event => edit({ title: event.target.value })}/></div>
        <div className="field"><label htmlFor="ticket-draft-body">{t("Ticket description")}</label><Textarea id="ticket-draft-body" rows={12} value={draft.body} maxLength={30000} disabled={busy} onChange={event => edit({ body: event.target.value })}/></div>
        {saved && <p role="status" className="text-sm">{t("Ticket draft saved.")}</p>}
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy || !draft.title.trim()} onClick={() => action("save")}>{t("Save")}</Button>
          <Button variant="outline" disabled={busy || !draft.title.trim()} onClick={() => action("download")}>{t("Download draft")}</Button>
          <Button variant="ghost" disabled={busy || !draft.title.trim()} onClick={() => action("copy")}>{t("Copy draft")}</Button>
          <Button variant="outline" disabled={busy || working || !!value.validated_version || !draft.title.trim()} onClick={() => action("analyze")}>{t(draft.source_version ? "Update analysis" : "Launch deep analysis")}</Button>
        </div>
        {draft.publication_available && draft.source_version && !dirty && draft.revision > 0 && <PublishTicket requestId={value.id} version={draft.source_version} triggerLabel="Publish ticket" preparedDraft={{ title: draft.title, body: draft.markdown }}/>}
        {!draft.publication_available && <p className="text-xs muted">{t("The draft can be saved and exported. External publication still requires a verified change analysis.")}</p>}
      </div>}
    </dialog>
  </>;
}
