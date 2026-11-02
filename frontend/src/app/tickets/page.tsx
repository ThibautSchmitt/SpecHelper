"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, RefreshCw, SlidersHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type Publication = {
  id:string; title:string; platform:string; project:string; connector_name:string;
  external_id:string; external_key:string; url:string; environment_name:string;
  published_at:string; request_id:string; analysis_deleted?:boolean;
};
type TicketList = {items:Publication[];total:number;page:number;page_size:number;environments:string[]};
const platformName=(value:string)=>({github:"GitHub",gitlab:"GitLab",jira:"Jira",glpi:"GLPI"})[value]||value;
function safeUrl(value:string) {
  try {
    const url=new URL(value);
    return ["http:","https:"].includes(url.protocol)&&!url.username&&!url.password&&!/[\\\s]/.test(value)?url.href:null;
  }catch{return null;}
}

export default function TicketsPage() {
  const {t,dateLocale}=useI18n();
  const [data,setData]=useState<TicketList>({items:[],total:0,page:1,page_size:25,environments:[]});
  const [platform,setPlatform]=useState("");
  const [environment,setEnvironment]=useState("");
  const [search,setSearch]=useState("");
  const [filters,setFilters]=useState(false);
  const [page,setPage]=useState(1);
  const [revision,setRevision]=useState(0);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const filtered=!!(search||platform||environment);
  useEffect(()=>{
    let alive=true;setLoading(true);
    const timer=setTimeout(()=>{
      api<TicketList>(`/tickets?${new URLSearchParams({platform,environment,search,page:String(page)})}`)
        .then(value=>{if(alive){setData(value);setError("");if(page>1&&!value.items.length)setPage(1);}})
        .catch(failure=>{if(alive)setError(failure.message);})
        .finally(()=>{if(alive)setLoading(false);});
    },200);
    return()=>{alive=false;clearTimeout(timer);};
  },[platform,environment,search,page,revision]);
  return <div className="space-y-5 min-w-0">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><h1>{t("Published tickets")}</h1><p className="mt-2 muted">{t("Find tickets created from SpecHelper on your external platforms.")}</p></div>
      <Button variant="ghost" size="sm" disabled={loading} onClick={()=>setRevision(value=>value+1)}><RefreshCw size={15} aria-hidden="true"/>{t("Refresh")}</Button>
    </header>
    {(data.total>0||filtered||loading||error)&&<div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="w-full sm:max-w-xs"><label className="sr-only" htmlFor="ticket-search">{t("Search tickets")}</label><Input id="ticket-search" value={search} placeholder={t("Title, reference, platform or project")} onChange={event=>{setSearch(event.target.value);setPage(1);}}/></div>
        <Button variant="outline" size="sm" aria-expanded={filters} aria-controls="ticket-filters" onClick={()=>setFilters(value=>!value)}><SlidersHorizontal size={14} aria-hidden="true"/>{t("Filters")}{(platform||environment)&&" •"}</Button>
      </div>
      {filters&&<div id="ticket-filters" className="flex flex-wrap gap-3">
        <div><label htmlFor="ticket-platform">{t("Platform")}</label><select id="ticket-platform" value={platform} onChange={event=>{setPlatform(event.target.value);setPage(1);}}><option value="">{t("All platforms")}</option>{["github","gitlab","jira","glpi"].map(value=><option key={value} value={value}>{platformName(value)}</option>)}</select></div>
        <div><label htmlFor="ticket-environment">{t("Environment")}</label><select id="ticket-environment" value={environment} onChange={event=>{setEnvironment(event.target.value);setPage(1);}}><option value="">{t("All environments")}</option>{data.environments.map(name=><option key={name} value={name}>{name}</option>)}</select></div>
      </div>}
    </div>}
    {error&&<div role="alert"><p>{t(error)}</p><p className="text-sm muted">{t("Refresh to try again. Previously loaded records may be out of date.")}</p></div>}
    {loading&&<p role="status" className="text-sm muted">{t("Loading tickets…")}</p>}
    {!loading&&!error&&!data.items.length&&<div className="text-sm muted"><p>{t(filtered?"No published tickets match these filters.":"No published tickets yet.")}</p>{!filtered&&<p className="mt-1">{t("Tickets published from your conversations will appear here.")}</p>}</div>}
    {!!data.items.length&&<Card className="overflow-hidden p-0">
      <ul className="divide-y" aria-label={t("Published tickets")} aria-busy={loading}>{data.items.map(ticket=>{
        const url=safeUrl(ticket.url);
        return <li key={ticket.id} data-ticket={ticket.id} className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold break-words [overflow-wrap:anywhere]">{url?<a className="text-primary hover:underline" href={url} target="_blank" rel="noopener noreferrer">{ticket.title}</a>:ticket.title}</h2>
              <p className="mt-1 text-xs muted break-words">{[platformName(ticket.platform),ticket.external_key||ticket.external_id,ticket.environment_name].filter(Boolean).join(" · ")}</p>
              <p className="mt-1 text-xs muted">{new Date(ticket.published_at).toLocaleString(dateLocale)}{ticket.connector_name&&` · ${ticket.connector_name}`}</p>
              {!ticket.analysis_deleted&&<Link className="mt-2 inline-block text-xs muted underline" href={`/analyses/${ticket.request_id}`}>{t("Source conversation")}</Link>}
            </div>
            {url?<Button variant="outline" size="sm" asChild><a href={url} target="_blank" rel="noopener noreferrer"><ExternalLink size={14} aria-hidden="true"/>{t("Open")}</a></Button>:<p className="text-xs muted">{t("External link unavailable")}</p>}
          </div>
        </li>;
      })}</ul>
      {(data.total>data.page_size||page>1)&&<div className="border-t p-3 flex items-center justify-between gap-3">
        <Button variant="ghost" size="sm" disabled={page===1||loading} onClick={()=>setPage(value=>value-1)}>{t("Previous")}</Button><p className="text-xs muted">{t("Page {page} · {total} tickets",{page,total:data.total})}</p><Button variant="ghost" size="sm" disabled={page*data.page_size>=data.total||loading} onClick={()=>setPage(value=>value+1)}>{t("Next")}</Button>
      </div>}
    </Card>}
  </div>;
}
