"use client";

import { useEffect, useId, useRef, useState } from "react";
import { FileText, LoaderCircle, X } from "lucide-react";
import { api, send, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PublishTicket } from "@/components/publish-ticket";

type Draft={id?:string|null;read_only?:boolean;revision:number;discussion_revision:number;source_version:number|null;source_verified:boolean;ticket_verified?:boolean;
 title:string;body:string;markdown:string;topic_message_id?:number;anchor_message_id?:number;context_message_ids?:number[];
 clarification?:string;
 scope_choice:"unknown"|"covered"|"clarified"|"changed";limitations:string[];
 generation?:{id:number;status:string;error:string;waiting_reason:string}|null;};
export function TicketPreparation({value,onUpdated,sourceVersion,ticketId,anchorMessageId,autoOpen=false,hideTrigger=false,onClosed,triggerLabel="Prepare a ticket"}:{
 value:RequestDetail;onUpdated:(value:RequestDetail)=>void;sourceVersion?:number;ticketId?:string;anchorMessageId?:number;
 autoOpen?:boolean;hideTrigger?:boolean;onClosed?:()=>void;triggerLabel?:string;
}){
 const {t}=useI18n();const dialog=useRef<HTMLDialogElement>(null);const prefix=useId();
 const [open,setOpen]=useState(false);const [draft,setDraft]=useState<Draft|null>(null);
 const [busy,setBusy]=useState(false);const [dirty,setDirty]=useState(false);const [saved,setSaved]=useState(false);const [error,setError]=useState("");
 const [publishing,setPublishing]=useState(false);const generated=useRef(false);
 const selected=useRef(ticketId||"");const endpoint=`/analyses/${value.id}/ticket-preparation`;
 const working=!!value.archived_at||(value.conversation_state?value.conversation_state!=="DISCUSSION":["QUEUED","UNDERSTANDING","ANALYZING","REVIEWING","GENERATING_RESULT","NEEDS_CLARIFICATION"].includes(value.status));
 const generating=!!draft?.generation&&["QUEUED","RUNNING"].includes(draft.generation.status);
 function draftUrl(){return endpoint+"?"+new URLSearchParams(selected.current?{ticket_id:selected.current}:{new_ticket:"true",...(sourceVersion?{source_version:String(sourceVersion)}:{}),...(anchorMessageId?{anchor_message_id:String(anchorMessageId)}:{})});}
 async function load(){
  setBusy(true);setError("");
  try{const next=await api<Draft>(draftUrl());setDraft(next);selected.current=next.id||"";setDirty(false);setSaved(false);}
  catch(failure){setError((failure as Error).message);}finally{setBusy(false);}
 }
 function show(){if(!ticketId){selected.current="";generated.current=false;}dialog.current?.showModal();setOpen(true);void load();}
 useEffect(()=>{if(autoOpen)show();/* explicit saved-message navigation only */
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 useEffect(()=>{
  if(!open||!generating)return;let alive=true;
  const timer=setInterval(async()=>{try{const next=await api<Draft>(draftUrl());if(alive){setDraft(next);if(next.generation?.status==="ERROR")setError(next.generation.error);}}catch(failure){if(alive)setError((failure as Error).message);}},2000);
  return()=>{alive=false;clearInterval(timer);};
 },[open,generating,endpoint]);
 useEffect(()=>{if(!open||!dirty)return;const protect=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};window.addEventListener("beforeunload",protect);return()=>window.removeEventListener("beforeunload",protect);},[open,dirty]);
 useEffect(()=>{if(open&&draft&&!draft.id&&anchorMessageId&&!busy&&!working&&!generated.current){generated.current=true;void action("generate");}
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[open,draft,busy,working]);
 function edit(changes:Partial<Draft>){setDraft(current=>current?{...current,...changes}:current);setDirty(true);setSaved(false);}
 async function persist(){
  if(!draft)throw new Error("Load the ticket draft first.");
  if(!dirty&&draft.id)return draft;
  const next=await send<Draft>(endpoint,{ticket_id:draft.id||undefined,new_ticket:!draft.id,
   expected_revision:draft.revision,expected_discussion_revision:draft.discussion_revision,source_version:draft.source_version,
   scope_choice:draft.scope_choice||"unknown",topic_message_id:draft.topic_message_id,anchor_message_id:draft.anchor_message_id||anchorMessageId,title:draft.title,body:draft.body},"PUT");
  setDraft(next);selected.current=next.id||"";setDirty(false);setSaved(true);onUpdated(await api<RequestDetail>(`/analyses/${value.id}`));return next;
 }
 async function action(operation:"save"|"generate"|"publish"|"analyze"|"copy"|"download"|"cancelDraft"){
  if(operation==="generate"&&draft?.id&&!window.confirm(t("Replace the saved ticket content with a new AI draft?")))return;
  setBusy(true);setError("");
  try{
   if(operation==="cancelDraft"){onUpdated(await send<RequestDetail>(`/analyses/${value.id}/discussion/cancel`,{}));await load();return;}
   const current=await persist();
   if(operation==="publish")setPublishing(true);
   if(operation==="generate"){
    if(!current.topic_message_id)throw new Error("Choose a conversation subject before drafting.");
    onUpdated(await send<RequestDetail>(`${endpoint}/generate`,{ticket_id:current.id,expected_revision:current.revision,expected_discussion_revision:current.discussion_revision,source_version:current.source_version,topic_message_id:current.topic_message_id,anchor_message_id:current.anchor_message_id||anchorMessageId}));
    setDraft(await api<Draft>(draftUrl()));window.dispatchEvent(new Event("queue-updated"));
   }
   if(operation==="analyze"){
    onUpdated(await send<RequestDetail>(`/analyses/${value.id}/deep-analyze`,{expected_revision:current.discussion_revision,intent:"change",preparation_revision:current.revision,ticket_id:current.id,subject:current.title,topic_message_id:current.topic_message_id}));
    dialog.current?.close();window.dispatchEvent(new Event("queue-updated"));
   }
   if(operation==="copy")await navigator.clipboard.writeText(current.markdown);
   if(operation==="download"){
    const url=URL.createObjectURL(new Blob([current.markdown],{type:"text/markdown;charset=utf-8"}));const link=document.createElement("a");link.href=url;link.download=`ticket-${current.id}.md`;link.click();URL.revokeObjectURL(url);
   }
  }catch(failure){setError((failure as Error).message);}finally{setBusy(false);}
 }
 function close(){if(!busy&&(!dirty||window.confirm(t("Discard unsaved ticket edits?"))))dialog.current?.close();}
 return <>
  {!hideTrigger&&<Button size="sm" variant="outline" onClick={show}><FileText size={15} aria-hidden="true"/>{t(triggerLabel)}</Button>}
  <dialog ref={dialog} className="skill-drawer ticket-preparation-drawer" aria-labelledby={prefix+"-title"} onClose={()=>{setOpen(false);onClosed?.();}} onCancel={event=>{event.preventDefault();close();}}>
   <div className="flex h-full min-h-0 flex-col">
    <header className="flex shrink-0 items-center justify-between gap-4 border-b p-5"><h2 id={prefix+"-title"}>{t("Prepare a ticket")}</h2><Button variant="ghost" size="sm" aria-label={t("Close")} disabled={busy} onClick={close}><X size={18} aria-hidden="true"/></Button></header>
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-5 space-y-4">
     {error&&<div role="alert" className="text-sm"><p>{t(error)}</p><Button variant="ghost" disabled={busy} onClick={()=>void load()}>{t("Reload saved draft")}</Button></div>}
     {!draft&&busy&&<p role="status" className="muted">{t("Loading…")}</p>}
     {draft&&<>
      <p className="text-xs muted">{t((draft.ticket_verified??draft.source_verified)?"Deep analysis available":"Not independently verified")}</p>
      {draft.clarification&&<p role="status" className="text-sm">{draft.clarification}</p>}
      <div className="field"><label htmlFor={prefix+"-name"}>{t("Ticket title")}</label><Input id={prefix+"-name"} value={draft.title} maxLength={200} disabled={busy||generating||draft.read_only} onChange={event=>edit({title:event.target.value})}/></div>
      <div className="field"><label htmlFor={prefix+"-body"}>{t("Ticket description")}</label><Textarea id={prefix+"-body"} rows={14} value={draft.body} maxLength={30000} disabled={busy||generating||draft.read_only} onChange={event=>edit({body:event.target.value})}/></div>
      {generating?<div className="flex flex-wrap items-center gap-2 text-sm" role="status"><LoaderCircle size={15} className="animate-spin" aria-hidden="true"/>{t("Drafting the ticket…")}<Button variant="ghost" size="sm" disabled={busy} onClick={()=>action("cancelDraft")}>{t("Cancel drafting")}</Button></div>:<Button variant="ghost" size="sm" disabled={busy||working||draft.read_only} onClick={()=>action("generate")}>{t("Write from conversation")}</Button>}
      {saved&&<p role="status" className="text-sm">{t("Ticket draft saved.")}</p>}
      <details className="text-sm"><summary>{t("Sources and options")}</summary><div className="mt-3 space-y-3">
       {draft.anchor_message_id&&<a className="text-primary underline" href={`#message-${draft.anchor_message_id}`} onClick={close}>{t("Source message")}</a>}
       {draft.source_version&&<a className="block text-primary underline" href={`/analyses/${value.id}?version=${draft.source_version}`}>{t("Source deep analysis")}</a>}
       {!!draft.limitations?.length&&<ul>{draft.limitations.map((limit,index)=><li key={index}>{limit}</li>)}</ul>}
       <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={busy||working||generating} onClick={()=>action("analyze")}>{t("Launch deep analysis")}</Button><Button variant="ghost" disabled={busy||generating} onClick={()=>action("download")}>{t("Download draft")}</Button><Button variant="ghost" disabled={busy||generating} onClick={()=>action("copy")}>{t("Copy draft")}</Button></div>
      </div></details>
     </>}
    </div>
    <footer className="flex shrink-0 flex-wrap justify-end gap-2 border-t p-4">
     <Button variant="ghost" disabled={busy} onClick={close}>{t("Cancel")}</Button>
     <Button variant="outline" disabled={busy||generating||!draft?.title.trim()||draft.read_only} onClick={()=>action("save")}>{t("Save")}</Button>
     <Button disabled={busy||generating||!draft?.title.trim()||!draft.body.trim()} onClick={()=>action("publish")}>{t("Continue to publication")}</Button>
    </footer>
   </div>
   {publishing&&draft?.id&&<PublishTicket requestId={value.id} version={draft.source_version} conversationTicketId={draft.id} preparedSource autoOpen hideTrigger preparedDraft={{title:draft.title,body:draft.markdown}} onAnalyze={()=>action("analyze")} onClosed={()=>{setPublishing(false);void load();void api<RequestDetail>(`/analyses/${value.id}`).then(onUpdated);}}/>}
  </dialog>
 </>;
}
