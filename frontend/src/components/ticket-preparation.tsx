"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Copy, FileText, LoaderCircle, X } from "lucide-react";
import { api, send, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PublishTicket, type PublicationControls } from "@/components/publish-ticket";
import { MarkdownReader } from "@/components/markdown-reader";
import { DeepAnalysisDialog } from "@/components/deep-analysis-dialog";

type Proposal = {id:string; title:string; body:string; replacement?:boolean};
type Draft = {
  id?:string|null; active?:boolean; read_only?:boolean; revision:number; discussion_revision:number;
  source_version:number|null; source_verified:boolean; title:string; body:string; markdown:string;
  scope_choice:"unknown"|"covered"|"clarified"|"changed"; topic_message_id?:number;
  documents?:string[];
  initial_pending?:boolean; can_recover_publication?:boolean; unchanged?:boolean; clarification?:string; proposal?:Proposal|null;
  generation?:{id:number; status:string; error:string; waiting_reason:string}|null;
};
export function TicketPreparation({value,onUpdated,sourceVersion,ticketId,anchorMessageId,resume=false,autoOpen=false,hideTrigger=false,onClosed,triggerLabel="Prepare a ticket"}:{
  value:RequestDetail; onUpdated:(value:RequestDetail)=>void; sourceVersion?:number; ticketId?:string; anchorMessageId?:number;
  resume?:boolean; autoOpen?:boolean; hideTrigger?:boolean; onClosed?:()=>void; triggerLabel?:string;
}) {
  const {t}=useI18n();
  const dialog=useRef<HTMLDialogElement>(null);
  const bodyEditor=useRef<HTMLTextAreaElement>(null);
  const prefix=useId();
  const lastPurpose=useRef<"prepare"|"refresh"|"replace">("prepare");
  const [open,setOpen]=useState(false);
  const [draft,setDraft]=useState<Draft|null>(null);
  const [busy,setBusy]=useState(false);
  const [dirty,setDirty]=useState(false);
  const [saved,setSaved]=useState(false);
  const [error,setError]=useState("");
  const [retryGeneration,setRetryGeneration]=useState(false);
  const [choice,setChoice]=useState(false);
  const [showProposal,setShowProposal]=useState(true);
  const publication=useRef<PublicationControls>(null);
  const [publicationLocked,setPublicationLocked]=useState(false);
  const [destinationDirty,setDestinationDirty]=useState(false);
  const [copied,setCopied]=useState(false);
  const [analysisDraft,setAnalysisDraft]=useState<Draft|null>(null);
  const [bodyView,setBodyView]=useState<"preview"|"edit">("preview");
  const endpoint=`/analyses/${value.id}/ticket-preparation`;
  const working=!!value.archived_at || (value.conversation_state ? value.conversation_state!=="DISCUSSION" : ["QUEUED","UNDERSTANDING","ANALYZING","REVIEWING","GENERATING_RESULT","NEEDS_CLARIFICATION"].includes(value.status));
  const generating=!!draft?.generation&&["QUEUED","RUNNING"].includes(draft.generation.status);
  const proposed=showProposal&&draft?.proposal;
  const readonly=!!draft?.read_only||generating||busy||publicationLocked;
  useEffect(()=>{
    const input=bodyEditor.current;
    if(input){input.style.height="auto";input.style.height=`${input.scrollHeight}px`;}
  },[bodyView,draft?.body,proposed&&proposed.body]);

  async function refreshConversation() {
    onUpdated(await api<RequestDetail>(`/analyses/${value.id}`));
    window.dispatchEvent(new Event("queue-updated"));
  }
  async function load(identifier?:string) {
    const next=await api<Draft>(endpoint+(identifier?`?ticket_id=${identifier}`:""));
    setDraft(next);setDirty(false);setSaved(false);
    return next;
  }
  async function generate(current:Draft,purpose:"prepare"|"refresh"|"replace") {
    lastPurpose.current=purpose;
    setBusy(true);setError("");setRetryGeneration(false);setChoice(false);
    try {
      onUpdated(await send<RequestDetail>(`${endpoint}/generate`,{
        ticket_id:current.id||undefined, expected_revision:current.revision,
        expected_discussion_revision:current.discussion_revision, purpose,
        replace_confirmed:purpose==="replace", anchor_message_id:anchorMessageId, source_version:sourceVersion,
      }));
      await load();setShowProposal(true);
      window.dispatchEvent(new Event("queue-updated"));
    } catch(failure) {setError((failure as Error).message);setRetryGeneration(true);}
    finally {setBusy(false);}
  }
  async function show() {
    dialog.current?.showModal();setOpen(true);setBusy(true);setError("");setRetryGeneration(false);setPublicationLocked(false);setCopied(false);setShowProposal(true);setBodyView("preview");
    try {
      const next=await load(ticketId);
      if(next.read_only||value.archived_at) {
        setChoice(false);
      } else if(next.id&&!next.initial_pending) {
        setChoice(!resume&&!ticketId&&!autoOpen);
      } else if(!next.generation||!["QUEUED","RUNNING"].includes(next.generation.status)) {
        await generate(next,"prepare");
      }
    } catch(failure) {setError((failure as Error).message);}
    finally {setBusy(false);}
  }
  useEffect(()=>{if(autoOpen)void show();
    // Explicit navigation to the saved draft opens it once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[]);
  useEffect(()=>{
    if(!open||!generating)return;
    let alive=true;
    const timer=setInterval(async()=>{
      try {
        const next=await api<Draft>(endpoint);
        if(!alive)return;
        setDraft(next);
        if(next.generation?.status==="ERROR"){setError(next.generation.error);setRetryGeneration(true);}
        if(!next.generation||!["QUEUED","RUNNING"].includes(next.generation.status))await refreshConversation();
      } catch(failure) {if(alive)setError((failure as Error).message);}
    },1500);
    return()=>{alive=false;clearInterval(timer);};
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[open,generating,endpoint]);
  useEffect(()=>{
    if(!open||!dirty&&!destinationDirty)return;
    const protect=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",protect);
    return()=>window.removeEventListener("beforeunload",protect);
  },[open,dirty,destinationDirty]);
  function edit(changes:Partial<Draft>) {
    setDraft(current=>current?{...current,...changes}:current);setDirty(true);setSaved(false);setCopied(false);
  }
  async function persist() {
    if(!draft)throw new Error("Load the ticket draft first.");
    if(!dirty&&draft.id)return draft;
    const next=await send<Draft>(endpoint,{
      ticket_id:draft.id||undefined, expected_revision:draft.revision,
      expected_discussion_revision:draft.discussion_revision, source_version:draft.source_version,
      scope_choice:draft.scope_choice||"unknown", topic_message_id:draft.topic_message_id,
      title:draft.title, body:draft.body,
      documents:draft.documents||["goal"],
    },"PUT");
    setDraft(next);setDirty(false);setSaved(true);await refreshConversation();
    return next;
  }
  async function action(kind:"save"|"refresh"|"analyze") {
    setBusy(true);setError("");setRetryGeneration(false);
    try {
      const current=await persist();
      await publication.current?.save(current);
      if(kind==="save")setSaved(true);
      if(kind==="refresh")await generate(current,"refresh");
      if(kind==="analyze") {
        setAnalysisDraft(current);
      }
    } catch(failure) {setError((failure as Error).message);}
    finally {setBusy(false);}
  }
  async function decide(apply:boolean) {
    if(!draft?.proposal)return;
    setBusy(true);setError("");
    try {
      const next=await send<Draft>(`${endpoint}/proposal`,{
        ticket_id:draft.id, proposal_id:draft.proposal.id, expected_revision:draft.revision,
        apply, replace_confirmed:apply&&!!draft.proposal.replacement,
      });
      setDraft(next);setShowProposal(true);setSaved(apply);await refreshConversation();
    } catch(failure) {setError((failure as Error).message);}
    finally {setBusy(false);}
  }
  async function close() {
    if(busy||generating)return;
    if(publication.current){await publication.current.close();return;}
    try{if(dirty)await persist();dialog.current?.close();}
    catch(failure){setError((failure as Error).message);}
  }
  async function copy() {
    if(!draft)return;
    try{await navigator.clipboard.writeText(`# ${draft.title}\n\n${draft.body}`);setCopied(true);}
    catch{setError("The draft could not be copied.");}
  }
  return <>
    {!hideTrigger&&<Button size="sm" variant={resume?"ghost":"outline"} onClick={()=>void show()}><FileText size={15} aria-hidden="true"/>{t(triggerLabel)}</Button>}
    <dialog ref={dialog} className="ticket-preparation-modal" aria-labelledby={prefix+"-heading"}
      onClose={()=>{setOpen(false);setChoice(false);onClosed?.();}}
      onCancel={event=>{event.preventDefault();void close();}}>
      <header className="ticket-modal-header">
        <div className="flex flex-wrap items-center gap-2"><h2 id={prefix+"-heading"}>{t("Create ticket")}</h2><span className="badge">{t("Draft")}</span></div>
        <Button variant="ghost" size="sm" aria-label={t("Close")} disabled={busy} onClick={close}><X size={18} aria-hidden="true"/></Button>
      </header>
      <div className="p-5 space-y-4">
        {error&&<div role="alert" className="text-sm"><p>{t(error)}</p>{retryGeneration&&<Button variant="ghost" disabled={busy||generating} onClick={()=>draft&&void generate(draft,lastPurpose.current)}>{t("Retry")}</Button>}</div>}
        {choice&&draft?<>
          <p>{t("A draft already exists: {title}. Resume it or replace it with a ticket for the current need?",{title:draft.title})}</p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={()=>setChoice(false)}>{t("Resume draft")}</Button>
            <Button variant="outline" disabled={busy||generating||working||draft.read_only} onClick={()=>void generate(draft,"replace")}>{t("Replace draft")}</Button>
            <Button variant="ghost" onClick={close}>{t("Cancel")}</Button>
          </div>
        </>:<>
          {(busy&&!draft||generating)&&<p role="status" className="flex items-center gap-2 text-sm"><LoaderCircle size={16} className="animate-spin" aria-hidden="true"/>{t(generating&&draft?.body?"Updating the draft…":"Preparing the ticket…")}</p>}
          {draft?.clarification&&<p role="status" className="text-sm">{draft.clarification}</p>}
          {draft&&!draft.initial_pending&&<>
            {draft.proposal&&<div className="text-sm space-y-2"><p>{t("AI update ready. Your draft is unchanged until you apply it.")}</p><Button variant="ghost" size="sm" onClick={()=>setShowProposal(!showProposal)}>{t(showProposal?"See my draft":"See proposed update")}</Button></div>}
            {draft.unchanged&&<p role="status" className="text-sm muted">{t("No relevant changes were found. Your draft was kept.")}</p>}
            <div className="field"><label htmlFor={prefix+"-title"}>{t("Title")}</label><Input id={prefix+"-title"} value={proposed?proposed.title:draft.title} maxLength={200} readOnly={!!draft.proposal} disabled={readonly} onChange={event=>edit({title:event.target.value})}/></div>
            <div className="field">
              <div className="reader-field-heading">
                {bodyView==="edit"?<label htmlFor={prefix+"-body"}>{t("Description")}</label>:<span className="font-medium">{t("Description")}</span>}
                <Button type="button" variant="ghost" size="sm" disabled={readonly||working||!!draft.proposal||!draft.id} onClick={()=>void action("refresh")}>{t("Improve with AI")}</Button>
                <div className="reader-view-switch" role="group" aria-label={t("Ticket display")}>
                  <button type="button" aria-pressed={bodyView==="preview"} onClick={()=>setBodyView("preview")}>{t("Preview")}</button>
                  <button type="button" aria-pressed={bodyView==="edit"} onClick={()=>setBodyView("edit")}>{t("Edit")}</button>
                </div>
              </div>
              {bodyView==="edit"?<Textarea ref={bodyEditor} className="ticket-description-editor" id={prefix+"-body"} rows={6} value={proposed?proposed.body:draft.body} maxLength={30000} readOnly={!!draft.proposal} disabled={readonly} onChange={event=>edit({body:event.target.value})}/>:<section className="ticket-description-reader" aria-label={t("Description")}><MarkdownReader>{proposed?proposed.body:draft.body}</MarkdownReader></section>}
            </div>
            {open&&draft.id&&<PublishTicket requestId={value.id} version={draft.source_version} conversationTicketId={draft.id}
              preparedSource autoOpen hideTrigger embedded unified controller={publication}
              preparedDraft={{title:draft.title,body:draft.body}} documents={draft.documents||["goal"]}
              beforeSave={persist} disabled={busy||generating||!!draft.read_only||!!draft.proposal} hideFooter={!!draft.proposal}
              onDocumentsChange={documents=>edit({documents})} onLockedChange={setPublicationLocked} onDirtyChange={setDestinationDirty}
              onClosed={()=>{dialog.current?.close();void refreshConversation();}}
              onPublished={()=>{dialog.current?.close();void refreshConversation();}}
              footerActions={<>
                <Button type="button" variant="ghost" disabled={busy||generating} onClick={()=>void copy()}><Copy size={14} aria-hidden="true"/>{t("Copy draft")}</Button>
                <Button type="button" variant="outline" disabled={readonly||!dirty&&!destinationDirty||!draft.title.trim()||!draft.body.trim()} onClick={()=>void action("save")}>{t("Save")}</Button>
              </>}
              advancedContent={<section className="text-xs muted" aria-label={t("Need verification")}>
                <p>{t(draft.source_verified?"Relevant deep analysis available":"Without deep verification")} · {t("Optional")}</p>
                <Button type="button" variant="ghost" size="sm" disabled={readonly||working||!!draft.proposal} onClick={()=>void action("analyze")}>{t("Launch deep analysis")}</Button>
              </section>}
            />}
            {copied&&<p role="status" className="text-sm">{t("Draft copied.")}</p>}
            {saved&&<p role="status" className="text-sm">{t("Ticket draft saved.")}</p>}
          </>}
        </>}
      </div>
      {!choice&&(!draft?.id||draft.initial_pending||!!draft.proposal)&&<footer className="ticket-modal-footer">
        <Button variant="ghost" disabled={busy} onClick={close}>{t("Close")}</Button>
        {draft?.proposal?<>
          <Button variant="outline" disabled={busy||generating||dirty} onClick={()=>void decide(false)}>{t("Keep my draft")}</Button>
          <Button disabled={busy||generating||dirty||!showProposal} onClick={()=>void decide(true)}>{t(draft.proposal.replacement?"Replace draft":"Apply")}</Button>
        </>:null}
      </footer>}
    </dialog>
    {analysisDraft?.id&&<DeepAnalysisDialog value={value} initialSubject={analysisDraft.title} preparation={{id:analysisDraft.id,revision:analysisDraft.revision,discussion_revision:analysisDraft.discussion_revision}} onUpdated={onUpdated} onClosed={()=>setAnalysisDraft(null)} onStarted={()=>{dialog.current?.close();}}/>}
  </>;
}
