"use client";

import { useRef, useState } from "react";
import { Send, Square, Sparkles, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, send, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { conversationState } from "@/lib/conversation-state";

export function DiscussionComposer({value,onUpdated}:{value:RequestDetail;onUpdated:(value:RequestDetail)=>void}) {
  const {t}=useI18n();
  const [text,setText]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [files,setFiles]=useState<File[]>([]);
  const [uploaded,setUploaded]=useState(0);
  const scopeDialog=useRef<HTMLDialogElement>(null);
  const [subject,setSubject]=useState("");
  const [selectedMessages,setSelectedMessages]=useState<number[]>([]);
  const inputs=(value.messages||[]).filter(message=>message.role==="user"&&!["ticket_preparation","derived_request"].includes(message.kind));
  const activeOperation=["IN_PROGRESS","WAITING_AI"].includes(conversationState(value));
  const working=!!value.archived_at || activeOperation;
  const deepRetry=value.discussion?.mode === "analysis" && !!value.analysis_runs?.length;
  async function action(operation:"message"|"deep"|"cancel"|"retry"|"start") {
    setBusy(true);setError("");
    try {
      if(operation === "retry" && deepRetry){
        onUpdated(await send<RequestDetail>(`/${value.workflow === "question" ? "questions" : "requests"}/${value.id}/retry`, {}));
        window.dispatchEvent(new Event("queue-updated"));
        return;
      }
      const revision=value.discussion?.revision || 0;
      if(operation === "message" || operation === "retry")for(let index=uploaded;index<files.length;index++){
        const body=new FormData();body.append("file",files[index]);
        await api(`/analyses/${value.id}/attachments`,{method:"POST",body});setUploaded(index+1);
      }
      const updated=await send<RequestDetail>(`/analyses/${value.id}/${operation === "start" ? "analyze" : operation === "cancel" ? value.discussion?.mode === "discussion" ? "discussion/cancel" : "cancel" : operation === "deep" ? "deep-analyze" : "discussion"}`,
        operation === "cancel" || operation === "start" ? {} : operation === "deep" ? {expected_revision:revision,intent:"auto",subject,message_ids:selectedMessages,topic_message_id:selectedMessages.length?Math.max(...selectedMessages):undefined} : {
          message:text,expected_revision:revision,
          restart_session:operation === "retry",
        });
      onUpdated(updated);setText("");setFiles([]);setUploaded(0);
      if(operation === "deep")scopeDialog.current?.close();
      window.dispatchEvent(new Event("queue-updated"));
    } catch (failure) {setError((failure as Error).message);} finally {setBusy(false);}
  }
  return <div className="space-y-3">
    {value.discussion?.has_new_messages && value.latest_version && <p className="text-xs muted">{t("New messages are not covered by the previous analysis.")}</p>}
    {error && <p role="alert" className="text-sm text-red-700">{t(error)}</p>}
    {value.discussion?.mode === "discussion" && value.discussion.job?.waiting_reason && <p className="text-xs muted">{t(value.discussion.job.waiting_reason)}</p>}
    <form className="conversation-composer conversation-compose-form" onSubmit={event=>{event.preventDefault();if(text.trim())void action("message");}}>
      <label className="cursor-pointer p-2" title={t("Attach files")}><Paperclip size={19} aria-hidden="true"/><span className="sr-only">{t("Attach files")}</span><input className="sr-only" type="file" multiple disabled={busy||working||uploaded>0} onChange={event=>setFiles(Array.from(event.target.files||[]))}/></label>
      <div className="field"><label className="sr-only" htmlFor="discussion-message">{t("Your message")}</label>
      <Textarea id="discussion-message" rows={2} maxLength={30000} value={text} onChange={event=>setText(event.target.value)}
        placeholder={t(working ? "The assistant is working…" : "Write your message…")} disabled={busy || working}
        onKeyDown={event=>{if(event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing){event.preventDefault();if(text.trim()&&!working&&!busy)event.currentTarget.form?.requestSubmit();}}}/></div>
      <Button className="conversation-send" type="submit" disabled={busy || working || !text.trim()} aria-label={t("Send message")}><Send size={20} aria-hidden="true"/></Button>
    </form>
    {!!files.length&&<p className="text-xs muted">{files.map(file=>file.name).join(" · ")}</p>}
    <div className="flex flex-wrap items-center gap-2">
      {value.status === "DRAFT" && value.discussion?.enabled && value.discussion.revision === 0 && <Button size="sm" disabled={busy||working||!!text.trim()||!!files.length} onClick={()=>action("start")}>{t("Start discussion")}</Button>}
      <Button size="sm" variant="outline" disabled={busy || working || !!text.trim() || !!files.length} title={text.trim() || files.length ? t("Send your draft before starting deep analysis.") : undefined} onClick={()=>{
        const latest=inputs.at(-1);setSubject(latest?.content||value.need);setSelectedMessages(latest?[latest.id]:[]);setError("");scopeDialog.current?.showModal();
      }}><Sparkles size={15} aria-hidden="true"/>{t("Launch deep analysis")}</Button>
      {activeOperation && <Button size="sm" variant="ghost" disabled={busy} onClick={()=>action("cancel")}><Square size={13} aria-hidden="true"/>{t("Cancel")}</Button>}
      {((["ERROR","CANCELLED"].includes(value.status) && (deepRetry || value.discussion?.job?.operation !== "ticket_preparation")) || error === "The selected AI configuration changed. Start a new discussion session explicitly.") && <Button size="sm" variant="outline" disabled={busy || !!value.archived_at || (deepRetry && (!!text.trim() || !!files.length))} onClick={()=>action("retry")}>{t("Retry")}</Button>}
    </div>
    <dialog ref={scopeDialog} className="publication-dialog" aria-labelledby="deep-scope-title" onCancel={event=>{if(busy)event.preventDefault();}}>
      <h2 id="deep-scope-title">{t("Deep analysis scope")}</h2>
      <p className="mt-2 text-sm muted">{t("Choose the need and relevant messages. Previous assistant replies are not verified facts.")}</p>
      <form className="mt-4 space-y-4" onSubmit={event=>{event.preventDefault();void action("deep");}}>
        <div className="field"><label htmlFor="deep-subject">{t("Need to investigate")}</label><Textarea id="deep-subject" rows={4} maxLength={30000} required disabled={busy} value={subject} onChange={event=>setSubject(event.target.value)}/></div>
        <fieldset disabled={busy}><legend className="text-sm font-medium">{t("Relevant user messages")}</legend><div className="mt-2 max-h-56 space-y-3 overflow-y-auto rounded-lg border p-3">{inputs.map(message=><label key={message.id} className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={selectedMessages.includes(message.id)} disabled={!selectedMessages.includes(message.id)&&selectedMessages.length>=100} onChange={event=>setSelectedMessages(previous=>event.target.checked?[...previous,message.id]:previous.filter(id=>id!==message.id))}/><span className="min-w-0 whitespace-pre-wrap break-words">{message.content}</span></label>)}</div></fieldset>
        {error&&<p role="alert" className="text-sm text-red-700">{t(error)}</p>}
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={busy} onClick={()=>scopeDialog.current?.close()}>{t("Cancel")}</Button><Button disabled={busy||!subject.trim()}>{t("Launch deep analysis")}</Button></div>
      </form>
    </dialog>
  </div>;
}
