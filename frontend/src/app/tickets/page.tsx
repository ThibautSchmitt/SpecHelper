"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { RefreshCw, SlidersHorizontal } from "lucide-react";
import { SafeMarkdown } from "@/components/safe-markdown";
import { TicketPreparation } from "@/components/ticket-preparation";
import { PublishTicket } from "@/components/publish-ticket";
import { api, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type Publication = {
  id:string; title:string; status:string; platform:string; project:string; connector_name?:string;
  external_id:string; external_key:string; url:string; error:string; created_at:string; updated_at?:string;
  body?:string; description?:string; request_id:string; version_number:number|null;
  conversation_ticket_id?:string; analysis_deleted?:boolean;
  attempt_history?:{status:string;error:string;observed_at:string;finished_at?:string|null}[];
};
type Ticket = Publication & {
  environment_name:string; kind?:string; conversation_title?:string; subject?:string;
  topic_message_id?:number; publications?:Publication[]; read_only?:boolean;
  labels?:string[]; payload_available?:boolean;
};
type TicketList = {items:Ticket[];total:number;page:number;page_size:number;environments?:string[]};
const statuses:Record<string,string>={DRAFT:"Draft",PUBLISHING:"Publication in progress",PENDING:"Publication in progress",PUBLISHED:"Published",ERROR:"Failed",FAILED:"Failed",UNCERTAIN:"Publication to verify"};
const colors:Record<string,string>={DRAFT:"DRAFT",PUBLISHING:"RUNNING",PENDING:"RUNNING",PUBLISHED:"DONE",ERROR:"ERROR",FAILED:"ERROR",UNCERTAIN:"PAUSED"};
const platformName=(value:string)=>({github:"GitHub",gitlab:"GitLab",jira:"Jira",glpi:"GLPI"})[value]||value;
function safeUrl(value:string) {try {const url=new URL(value);return ["http:","https:"].includes(url.protocol)?url.href:null;}catch{return null;}}

export default function TicketsPage() {
 const {t,dateLocale}=useI18n();
 const [data,setData]=useState<TicketList>({items:[],total:0,page:1,page_size:25});
 const [platform,setPlatform]=useState("");const [environment,setEnvironment]=useState("");
 const [status,setStatus]=useState("all");const [search,setSearch]=useState("");
 const [filters,setFilters]=useState(false);const [page,setPage]=useState(1);const [revision,setRevision]=useState(0);
 const [selectedId,setSelectedId]=useState<string|null>(null);const [detail,setDetail]=useState<Ticket|null>(null);
 const [loading,setLoading]=useState(true);const [detailLoading,setDetailLoading]=useState(false);
 const [error,setError]=useState("");const [detailError,setDetailError]=useState("");
 const [editor,setEditor]=useState<{value:RequestDetail;ticketId:string}|null>(null);const [opening,setOpening]=useState(false);
 const detailPanel=useRef<HTMLElement>(null);
 const selected=data.items.find(item=>item.id===selectedId);
 const date=(value:string)=>new Date(value).toLocaleString(dateLocale);
 const badge=(state:string)=><span className="badge" data-state={colors[state]||"DRAFT"}>{t(statuses[state]||state)}</span>;
 useEffect(()=>{
  let alive=true;setLoading(true);
  const timer=setTimeout(()=>{
   api<TicketList>(`/tickets?${new URLSearchParams({platform,environment,status,search,page:String(page)})}`)
    .then(value=>{if(alive){setData(value);setSelectedId(current=>value.items.some(item=>item.id===current)?current:value.items[0]?.id||null);setError("");}})
    .catch(failure=>{if(alive)setError(failure.message);}).finally(()=>{if(alive)setLoading(false);});
  },200);
  return()=>{alive=false;clearTimeout(timer);};
 },[platform,environment,status,search,page,revision]);
 useEffect(()=>{
  let alive=true;setDetail(null);setDetailError("");setDetailLoading(!!selectedId);
  if(selectedId)api<Ticket>(`/tickets/${selectedId}`).then(value=>{if(alive)setDetail(value);})
   .catch(failure=>{if(alive)setDetailError(failure.message);}).finally(()=>{if(alive)setDetailLoading(false);});
  return()=>{alive=false;};
 },[selectedId,revision]);
 // Refresh local publication records while an operation is being confirmed; no external polling.
 useEffect(()=>{
  if(!data.items.some(item=>item.status==="PUBLISHING"))return;
  const timer=setInterval(()=>setRevision(value=>value+1),5000);return()=>clearInterval(timer);
 },[data.items]);
 async function editTicket(ticket:Ticket) {
  setOpening(true);setDetailError("");
  try {setEditor({ticketId:ticket.conversation_ticket_id||ticket.id,value:await api<RequestDetail>(`/analyses/${ticket.request_id}`)});}
  catch(failure){setDetailError((failure as Error).message);}finally{setOpening(false);}
 }
 function choose(ticket:Ticket) {setSelectedId(ticket.id);requestAnimationFrame(()=>detailPanel.current?.scrollIntoView({block:"start",behavior:"smooth"}));}
 const publications=detail?.publications || (detail && (!detail.kind||detail.kind==="publication")?[detail]:[]);
 const filtered=!!(search||status!=="all"||platform||environment);
 return <div className="space-y-5 min-w-0">
  <header className="flex flex-wrap items-start justify-between gap-4">
   <div><h1>{t("Tickets")}</h1><p className="mt-2 muted">{t("Drafts and tickets published from your conversations.")}</p></div>
   <Button variant="ghost" size="sm" disabled={loading||detailLoading} onClick={()=>setRevision(value=>value+1)}><RefreshCw size={15} aria-hidden="true"/>{t("Refresh")}</Button>
  </header>
  {(data.total>0||filtered||loading||error) && <div className="space-y-3">
   <div className="flex flex-wrap items-end gap-3">
    <div className="w-full sm:max-w-xs"><label className="sr-only" htmlFor="ticket-search">{t("Search tickets")}</label><Input id="ticket-search" value={search} placeholder={t("Title, reference, destination or conversation")} onChange={event=>{setSearch(event.target.value);setPage(1);}}/></div>
    <div><label className="sr-only" htmlFor="ticket-status">{t("Publication status")}</label><select id="ticket-status" value={status} onChange={event=>{setStatus(event.target.value);setPage(1);}}><option value="all">{t("All statuses")}</option>{["DRAFT","PUBLISHING","PUBLISHED","ERROR","UNCERTAIN"].map(value=><option key={value} value={value}>{t(statuses[value])}</option>)}</select></div>
    <Button variant="outline" size="sm" aria-expanded={filters} aria-controls="ticket-filters" onClick={()=>setFilters(value=>!value)}><SlidersHorizontal size={14} aria-hidden="true"/>{t("Filters")}{(platform||environment)&&" •"}</Button>
   </div>
   {filters && <div id="ticket-filters" className="flex flex-wrap gap-3">
    <div><label htmlFor="ticket-platform">{t("Platform")}</label><select id="ticket-platform" value={platform} onChange={event=>{setPlatform(event.target.value);setPage(1);}}><option value="">{t("All platforms")}</option>{["github","gitlab","jira","glpi"].map(value=><option key={value} value={value}>{platformName(value)}</option>)}</select></div>
    <div><label htmlFor="ticket-environment">{t("Environment")}</label><select id="ticket-environment" value={environment} onChange={event=>{setEnvironment(event.target.value);setPage(1);}}><option value="">{t("All environments")}</option>{data.environments?.map(name=><option key={name} value={name}>{name}</option>)}</select></div>
   </div>}
  </div>}
  {error&&<div role="alert"><p>{t(error)}</p><p className="text-sm muted">{t("Refresh to try again. Previously loaded records may be out of date.")}</p></div>}
  {loading&&<p role="status" className="text-sm muted">{t("Loading tickets…")}</p>}
  {!loading&&!error&&!data.items.length&&<p className="muted"><span>{t(filtered?"No tickets match these filters.":"No tickets yet. Tickets prepared from your conversations will appear here.")}</span> <Link className="text-primary underline" href="/analyses">{t("View analyses")}</Link></p>}
  {!!data.items.length&&<Card className="overflow-hidden p-0" aria-label={t("Tickets")}>
   <ul className="divide-y" aria-label={t("Ticket list")} aria-busy={loading}>{data.items.map(ticket=>{
    const url=safeUrl(ticket.url);const confirmed=ticket.publications?.filter(item=>item.status==="PUBLISHED")||[];
    return <li key={ticket.id} className="p-4 sm:p-5" data-ticket={ticket.id}>
     <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 flex-1"><div className="title-tags"><button type="button" className="text-left font-semibold text-primary break-words [overflow-wrap:anywhere]" aria-pressed={selectedId===ticket.id} onClick={()=>choose(ticket)}>{ticket.title}</button>{badge(ticket.status)}</div>
       <p className="mt-1 text-xs muted break-words">{ticket.environment_name}{ticket.conversation_title&&` · ${ticket.conversation_title}`}</p>
       <p className="mt-1 text-xs muted">{date(ticket.updated_at||ticket.created_at)}</p>
       {!!confirmed.length&&<p className="mt-1 text-xs muted">{confirmed.map(item=>[platformName(item.platform),item.connector_name,item.external_key||item.external_id].filter(Boolean).join(" · ")).join(" / ")}</p>}
       {ticket.platform&&<p className="mt-1 text-xs muted">{[platformName(ticket.platform),ticket.connector_name,ticket.external_key||ticket.external_id||ticket.project].filter(Boolean).join(" · ")}</p>}
      </div>
      <div className="flex flex-wrap gap-2">
       {ticket.kind==="preparation"&&ticket.status==="DRAFT"&&!ticket.analysis_deleted&&<Button variant="outline" size="sm" disabled={opening} onClick={()=>editTicket(ticket)}>{t("Resume")}</Button>}
       {ticket.kind==="publication_draft"&&ticket.version_number&&!ticket.analysis_deleted&&<PublishTicket requestId={ticket.request_id} version={ticket.version_number} triggerLabel="Resume" onClosed={()=>setRevision(value=>value+1)}/>}
       {url&&<Button variant="outline" size="sm" asChild><a href={url} target="_blank" rel="noopener noreferrer">{t("View ticket")}</a></Button>}
       {ticket.kind==="preparation"&&confirmed.length===1&&safeUrl(confirmed[0].url)&&<Button variant="outline" size="sm" asChild><a href={safeUrl(confirmed[0].url)!} target="_blank" rel="noopener noreferrer">{t("View ticket")}</a></Button>}
       {["ERROR","FAILED","UNCERTAIN"].includes(ticket.status)&&<Button variant="outline" size="sm" onClick={()=>choose(ticket)}>{t(ticket.status==="UNCERTAIN"?"Verify publication":"See error")}</Button>}
      </div>
     </div>
    </li>;
   })}</ul>
   {(data.total>data.page_size||page>1)&&<div className="border-t p-3 flex items-center justify-between gap-3">
    <Button variant="ghost" size="sm" disabled={page===1||loading} onClick={()=>setPage(value=>value-1)}>{t("Previous")}</Button><p className="text-xs muted">{t("Page {page} · {total} tickets",{page,total:data.total})}</p><Button variant="ghost" size="sm" disabled={page*data.page_size>=data.total||loading} onClick={()=>setPage(value=>value+1)}>{t("Next")}</Button>
   </div>}
  </Card>}
  {selected&&<section ref={detailPanel} className="scroll-mt-4" aria-label={t("Selected ticket")}><Card className="p-4 sm:p-6 min-w-0">
   <header className="flex flex-wrap justify-between items-start gap-3"><h2 className="break-words [overflow-wrap:anywhere]">{selected.title}</h2>
    {selected.kind==="preparation"&&!selected.analysis_deleted&&<Button variant="outline" size="sm" disabled={opening||detailLoading} onClick={()=>editTicket(selected)}>{t(detail?.read_only?"Open ticket draft":"Modify")}</Button>}
   </header>
   {detailLoading&&<p role="status" className="mt-4 muted">{t("Loading ticket details…")}</p>}
   {detailError&&<p role="alert" className="mt-4">{t(detailError)}</p>}
   {!detailLoading&&detail&&<div className="mt-4 space-y-5">
    {detail.payload_available===false&&<p role="status" className="text-sm muted">{t("The submitted content is unavailable for this record. Publication metadata remains visible.")}</p>}
    <div data-testid="ticket-description"><SafeMarkdown>{detail.description||t("No description was stored.")}</SafeMarkdown></div>
    {!!detail.labels?.length&&<div className="flex flex-wrap gap-2">{detail.labels.map((label,index)=><span key={index} className="badge break-words">{label}</span>)}</div>}
    <div className="text-sm flex flex-wrap gap-3">
     {detail.analysis_deleted?<p className="muted">{t("Source analysis deleted · publication evidence preserved")}</p>:<>
      <Link className="text-primary underline" href={`/analyses/${detail.request_id}${detail.topic_message_id?`#message-${detail.topic_message_id}`:""}`}>{t("Source conversation")}</Link>
      {detail.version_number&&<Link className="text-primary underline" href={`/analyses/${detail.request_id}?version=${detail.version_number}`}>{t("Source analysis · v{number}",{number:detail.version_number})}</Link>}
     </>}
    </div>
    {detail.subject&&<details><summary>{t("Original need")}</summary><p className="mt-2 whitespace-pre-wrap text-sm">{detail.subject}</p></details>}
    {!!publications.length&&<section aria-label={t("Publications")} className="space-y-3 border-t pt-4"><h3>{t("Publications")}</h3>
     {publications.map(publication=><details key={publication.id} className="rounded-md border p-3" open={["ERROR","UNCERTAIN"].includes(publication.status)}>
      <summary className="cursor-pointer"><span className="inline-flex flex-wrap items-center gap-2">{[platformName(publication.platform),publication.connector_name,publication.project].filter(Boolean).join(" · ")}{badge(publication.status)}</span></summary>
      <div className="mt-3 space-y-3 text-sm">
       <p className="muted">{date(publication.updated_at||publication.created_at)}</p>
       {safeUrl(publication.url)&&<a className="text-primary underline" href={safeUrl(publication.url)!} target="_blank" rel="noopener noreferrer">{publication.external_key||publication.external_id||t("View ticket")}</a>}
       {publication.error&&<p role="alert">{t(publication.error)}</p>}
       {publication.status==="UNCERTAIN"&&<p>{t("The external ticket may already exist. Verification will not create another ticket.")}</p>}
       {!detail.analysis_deleted&&publication.version_number&&["ERROR","UNCERTAIN","PUBLISHING"].includes(publication.status)&&<PublishTicket requestId={detail.request_id} version={publication.version_number} conversationTicketId={detail.conversation_ticket_id} triggerLabel={publication.status==="ERROR"?"Retry":"Verify publication"} onClosed={()=>setRevision(value=>value+1)}/>}
       {!!publication.attempt_history?.length&&<details><summary>{t("Previous attempts")}</summary><ul className="mt-2 space-y-2">{publication.attempt_history.map((attempt,index)=><li key={index}>{badge(attempt.status)} <span className="muted">{date(attempt.finished_at||attempt.observed_at)}</span>{attempt.error&&<p>{t(attempt.error)}</p>}</li>)}</ul></details>}
       {publication.body&&<details><summary>{t("Submitted content")}</summary><div className="mt-2"><SafeMarkdown>{publication.body}</SafeMarkdown></div></details>}
      </div>
     </details>)}
     <p className="text-xs muted">{t("This is SpecHelper’s publication record, not a live external ticket status. Refresh reloads local records only.")}</p>
    </section>}
   </div>}
  </Card></section>}
  {editor&&<TicketPreparation key={editor.ticketId} value={editor.value} ticketId={editor.ticketId} autoOpen hideTrigger onClosed={()=>{setEditor(null);setRevision(value=>value+1);}} onUpdated={value=>{setEditor(current=>current?{...current,value}:null);setRevision(value=>value+1);}}/>}
 </div>;
}
