"use client";

import { useEffect, useRef, useState } from "react";
import { FileText, LoaderCircle } from "lucide-react";
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
  topic_message_id?: number; topics?: {id:number;label:string}[];
  discussion_findings_available?: boolean;
  generation?: {id:number;status:string;error:string;waiting_reason:string} | null;
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
  const [open, setOpen] = useState(false);
  const endpoint = `/analyses/${value.id}/ticket-preparation`;
  const working = ["QUEUED", "UNDERSTANDING", "ANALYZING", "REVIEWING", "GENERATING_RESULT", "CONTINUING_CONVERSATION", "GENERATING_TICKET", "NEEDS_CLARIFICATION"].includes(value.status);
  const generating = !!draft?.generation && ["QUEUED","RUNNING"].includes(draft.generation.status);
  useEffect(() => {
    if (!open || !generating) return;
    let alive = true;
    const timer = setInterval(async () => {
      try {
        const next = await api<Draft>(endpoint);
        if (alive) { setDraft(next); if (next.generation?.status === "ERROR") setError(next.generation.error); }
      } catch (failure) { if (alive) setError((failure as Error).message); }
    }, 2000);
    return () => { alive = false; clearInterval(timer); };
  }, [open, generating, endpoint]);

  async function load() {
    setBusy(true); setError(""); setDraft(null); setSaved(false);
    try { const next=await api<Draft>(endpoint); setDraft(next); setDirty(false); if(next.generation?.status==='ERROR')setError(next.generation.error); }
    catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  async function selectTopic(id:number) {
    if(dirty && !window.confirm(t("Discard unsaved ticket edits and change the subject?")))return;
    setBusy(true); setError(""); setSaved(false);
    try { setDraft(await api<Draft>(`${endpoint}?topic_message_id=${id}`)); setDirty(true); }
    catch(failure){setError((failure as Error).message);}
    finally{setBusy(false);}
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
      topic_message_id: draft.topic_message_id,
      title: draft.title, body: draft.body,
    }, "PUT");
    setDraft(updated); setDirty(false); setSaved(true);
    return updated;
  }
  async function action(operation: "save" | "copy" | "download" | "analyze" | "generate" | "cancelDraft") {
    setBusy(true); setError("");
    try {
      if(operation === "cancelDraft"){
        onUpdated(await send<RequestDetail>(`/analyses/${value.id}/discussion/cancel`, {}));
        setDraft(await api<Draft>(endpoint)); return;
      }
      const current = await persist();
      if(operation === "generate"){
        if(!current.topic_message_id)throw new Error("Choose a conversation subject before drafting.");
        onUpdated(await send<RequestDetail>(`${endpoint}/generate`, {
          expected_revision:current.revision, expected_discussion_revision:current.discussion_revision,
          source_version:current.source_version, topic_message_id:current.topic_message_id,
        }));
        setDraft(await api<Draft>(endpoint)); setSaved(false);
        window.dispatchEvent(new Event("queue-updated"));
      }
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
    <Button size="sm" variant="outline" onClick={() => { dialog.current?.showModal(); setOpen(true); void load(); }}><FileText size={15} aria-hidden="true"/>{t("Prepare a ticket")}</Button>
    <dialog ref={dialog} className="publication-dialog" aria-labelledby={`ticket-preparation-title-${value.id}`} onClose={()=>setOpen(false)} onCancel={event => { if (busy) event.preventDefault(); }}>
      <div className="flex items-start justify-between gap-4">
        <h2 id={`ticket-preparation-title-${value.id}`}>{t("Prepare a ticket")}</h2>
        <Button variant="ghost" disabled={busy} onClick={() => dialog.current?.close()}>{t(generating ? "Close" : "Cancel")}</Button>
      </div>
      <p className="mt-2 text-sm muted">{t("Preparing a draft does not launch an analysis or publish a ticket.")}</p>
      {error && <div className="mt-4" role="alert"><p>{t(error)}</p><Button variant="ghost" disabled={busy} onClick={load}>{t("Reload saved draft")}</Button></div>}
      {!draft && busy && <p className="mt-4" role="status">{t("Loading…")}</p>}
      {draft && <div className="mt-5 space-y-4">
        {!!draft.topics?.length && <div className="field"><label htmlFor="ticket-subject">{t("Ticket subject")}</label><select id="ticket-subject" value={draft.topic_message_id} disabled={busy||generating} onChange={event=>void selectTopic(Number(event.target.value))}>{draft.topics.map(topic=><option key={topic.id} value={topic.id}>{topic.label}</option>)}</select><p className="text-xs muted">{t("Select the question to include. Other subjects remain in the conversation.")}</p></div>}
        {draft.discussion_findings_available && <p className="text-sm muted">{t("Recorded discussion findings are available, even without a completed deep analysis.")}</p>}
        <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={busy||working||generating||!draft.topic_message_id} onClick={()=>action("generate")}>{t("Write from conversation")}</Button>{generating&&<><p role="status" className="flex items-center gap-2 text-sm"><LoaderCircle size={16} className="animate-spin" aria-hidden="true"/>{t(draft.generation?.waiting_reason||"Drafting the ticket…")}</p><Button variant="ghost" disabled={busy} onClick={()=>action("cancelDraft")}>{t("Cancel drafting")}</Button></>}</div>
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
        <div className="field"><label htmlFor="ticket-draft-title">{t("Ticket title")}</label><Input id="ticket-draft-title" value={draft.title} maxLength={200} disabled={busy||generating} onChange={event => edit({ title: event.target.value })}/></div>
        <div className="field"><label htmlFor="ticket-draft-body">{t("Ticket description")}</label><Textarea id="ticket-draft-body" rows={12} value={draft.body} maxLength={30000} disabled={busy||generating} onChange={event => edit({ body: event.target.value })}/></div>
        {saved && <p role="status" className="text-sm">{t("Ticket draft saved.")}</p>}
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy || generating || !draft.title.trim()} onClick={() => action("save")}>{t("Save")}</Button>
          <Button variant="outline" disabled={busy || generating || !draft.title.trim()} onClick={() => action("download")}>{t("Download draft")}</Button>
          <Button variant="ghost" disabled={busy || generating || !draft.title.trim()} onClick={() => action("copy")}>{t("Copy draft")}</Button>
          <Button variant="outline" disabled={busy || working || !!value.validated_version || !draft.title.trim()} onClick={() => action("analyze")}>{t(draft.source_version ? "Update analysis" : "Launch deep analysis")}</Button>
        </div>
        {draft.publication_available && draft.source_version && !dirty && draft.revision > 0 && <PublishTicket requestId={value.id} version={draft.source_version} triggerLabel="Publish ticket" preparedDraft={{ title: draft.title, body: draft.markdown }}/>}
        {!draft.publication_available && <p className="text-xs muted">{t("The draft can be saved and exported. External publication still requires a verified change analysis.")}</p>}
      </div>}
    </dialog>
  </>;
}
