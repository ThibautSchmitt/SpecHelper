"use client";

import { useEffect, useState } from "react";
import { ChevronDown, Send, Square, Sparkles, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, send, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Connection = {id:number; name:string; agent:string; enabled:boolean; roles:string[]; model:string};

export function DiscussionComposer({value,onUpdated}:{value:RequestDetail;onUpdated:(value:RequestDetail)=>void}) {
  const {t}=useI18n();
  const [text,setText]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [choices,setChoices]=useState<Connection[]>([]);
  const [selected,setSelected]=useState("");
  const [choose,setChoose]=useState(false);
  const [files,setFiles]=useState<File[]>([]);
  const [uploaded,setUploaded]=useState(0);
  const working=["QUEUED","UNDERSTANDING","ANALYZING","REVIEWING","GENERATING_RESULT","CONTINUING_CONVERSATION","GENERATING_TICKET"].includes(value.status);
  useEffect(()=>{api<Connection[]>("/ai-connections").then(setChoices).catch(()=>{});},[]);
  async function action(operation:"message"|"deep"|"change"|"cancel"|"retry"|"start") {
    setBusy(true);setError("");
    try {
      const revision=value.discussion?.revision || 0;
      if(operation === "message" || operation === "retry")for(let index=uploaded;index<files.length;index++){
        const body=new FormData();body.append("file",files[index]);
        await api(`/analyses/${value.id}/attachments`,{method:"POST",body});setUploaded(index+1);
      }
      const updated=await send<RequestDetail>(`/analyses/${value.id}/${operation === "start" ? "analyze" : operation === "cancel" ? value.discussion?.mode === "discussion" ? "discussion/cancel" : "cancel" : operation === "deep" || operation === "change" ? "deep-analyze" : "discussion"}`,
        operation === "cancel" || operation === "start" ? {} : operation === "deep" || operation === "change" ? {expected_revision:revision,intent:operation === "change" ? "change" : "auto"} : {
          message:text,expected_revision:revision,
          ...(selected ? {connection_id:Number(selected)} : {}),restart_session:operation === "retry",
        });
      onUpdated(updated);setText("");setSelected("");setChoose(false);setFiles([]);setUploaded(0);
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
      {value.status === "DRAFT" && value.discussion?.enabled && value.discussion.revision === 0 && <Button size="sm" disabled={busy||!!text.trim()||!!files.length} onClick={()=>action("start")}>{t("Start discussion")}</Button>}
      <Button size="sm" variant="outline" disabled={busy || working || !!text.trim() || !!files.length} title={text.trim() || files.length ? t("Send your draft before starting deep analysis.") : undefined} onClick={()=>action("deep")}><Sparkles size={15} aria-hidden="true"/>{t("Launch deep analysis")}</Button>
      {!value.latest_version && <Button size="sm" variant="ghost" disabled={busy || working || !!text.trim() || !!files.length} onClick={()=>action("change")}>{t("Prepare a ticket")}</Button>}
      <Button size="sm" variant="ghost" disabled={busy || working} onClick={()=>setChoose(!choose)} aria-expanded={choose}>{t("Change assistant")}<ChevronDown size={14} aria-hidden="true"/></Button>
      {working && <Button size="sm" variant="ghost" disabled={busy} onClick={()=>action("cancel")}><Square size={13} aria-hidden="true"/>{t("Cancel")}</Button>}
      {(["ERROR","CANCELLED"].includes(value.status) || error === "The selected AI configuration changed. Start a new discussion session explicitly.") && <Button size="sm" variant="outline" disabled={busy} onClick={()=>action("retry")}>{t("Resume with a new session")}</Button>}
    </div>
    {choose && <div className="max-w-sm space-y-2 text-sm"><label htmlFor="discussion-assistant">{t("Discussion assistant")}</label>
      <select id="discussion-assistant" value={selected || String(value.discussion?.connection_id || "")} onChange={event=>setSelected(event.target.value)}>
        <option value="">{t("Automatic selection")}</option>{choices.filter(c=>c.enabled&&c.roles.includes("analyst")).map(c=><option key={c.id} value={c.id}>{c.name || c.agent}{c.model ? ` · ${c.model}` : ""}</option>)}
      </select><p className="text-xs muted">{t("Changing the assistant starts a new native session on your next message. Conversation history is kept.")}</p>
    </div>}
  </div>;
}
