"use client";

import {useEffect,useState,type Dispatch,type SetStateAction} from "react";
import {ChevronDown,LoaderCircle} from "lucide-react";
import {api} from "@/lib/api";
import {useI18n} from "@/lib/i18n";
import type {SQLReceipt} from "@/lib/analysis-evidence";
import {CodeBlock,sourceLanguage} from "@/components/code-block";
import {MarkdownReader} from "@/components/markdown-reader";

type Source = Partial<SQLReceipt> & {
  id:string;kind:"sql"|"git"|"web"|"document";number?:number;title?:string;url?:string;
  excerpt?:string;note?:string;repository?:string;commit?:string;line_start?:number;line_end?:number;version?:number;
};
const labels={sql:"Database check",git:"Source code",web:"Web reference",document:"Document"};

function SourceExcerpt({source}:{source:Source}) {
  const {t}=useI18n();
  const [raw,setRaw]=useState(false);
  if(source.kind==="sql"||source.kind==="git")return <CodeBlock code={source.sql||source.excerpt||""} language={source.kind==="sql"?"sql":sourceLanguage(source.title)}/>;
  return <div className="source-reader">
    <div className="reader-view-switch" role="group" aria-label={t("Source display")}>
      <button type="button" aria-pressed={!raw} onClick={()=>setRaw(false)}>{t("Read")}</button>
      <button type="button" aria-pressed={raw} onClick={()=>setRaw(true)}>{t("Source text")}</button>
    </div>
    {raw?<CodeBlock code={source.excerpt||""}/>:<MarkdownReader>{source.excerpt||""}</MarkdownReader>}
  </div>;
}

export function SourceDetails({url,checks,referenceIds,selected,onSelect}:{url?:string;checks:SQLReceipt[];referenceIds:string[];selected:string[];onSelect:Dispatch<SetStateAction<string[]>>}){
  const {t}=useI18n();
  const [open,setOpen]=useState(false);
  const [attempt,setAttempt]=useState(0);
  const [sources,setSources]=useState<Source[]>([]);
  const [loaded,setLoaded]=useState(false);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{if(selected.length)setOpen(true);},[selected]);
  useEffect(()=>{setLoaded(false);setSources([]);setError("");},[url]);
  useEffect(()=>{
    if(!open||loaded||!url)return;
    let alive=true;setLoading(true);setError("");
    api<{sources:Source[]}>(url).then(result=>{if(alive){setSources(Array.isArray(result.sources)?result.sources:[]);setLoaded(true);setLoading(false);}}).catch(failure=>{if(alive){setError((failure as Error).message);setLoading(false);}});
    return()=>{alive=false;};
  },[open,loaded,url,attempt]);
  const unsuccessful=new Set([...sources.filter(source=>source.kind==='sql'&&(source.status==='rejected'||source.status==='unavailable')).map(source=>source.id),...checks.filter(check=>check.status==='rejected'||check.status==='unavailable').map(check=>check.query_id)]);
  const records=sources.filter(source=>!unsuccessful.has(source.id));
  for(const check of checks)if(!unsuccessful.has(check.query_id)&&!records.some(source=>source.id===check.query_id))records.push({...check,id:check.query_id,kind:"sql"});
  for(const id of referenceIds)if(!unsuccessful.has(id)&&!records.some(source=>source.id===id))records.push({id,kind:"sql",note:"The database-check record is unavailable."});
  function safeLink(value?:string){return value&&(/^https:\/\//i.test(value)||value.startsWith("/api/")&&!value.startsWith("//"))?value:undefined;}
  return <details className="source-details" open={open} onToggle={event=>{if(event.target!==event.currentTarget)return;setOpen(event.currentTarget.open);if(!event.currentTarget.open)onSelect([]);}}>
    <summary><ChevronDown size={15} aria-hidden="true"/>{t("Sources and checks")}</summary>
    {open&&<div className="source-details-content">
      {loading&&<p role="status" className="flex items-center gap-2 text-xs muted"><LoaderCircle size={14} className="animate-spin" aria-hidden="true"/>{t("Loading…")}</p>}
      {error&&<p role="alert" className="text-xs">{t(error)} <button type="button" className="underline" onClick={()=>setAttempt(current=>current+1)}>{t("Retry")}</button></p>}
      {!loading&&!error&&!records.length&&<p className="text-xs muted">{t("No source details were recorded for this answer.")}</p>}
      {records.map((source,index)=><details className="source-record" key={source.id} open={selected.includes(source.id)} onToggle={event=>{
        if(event.target!==event.currentTarget)return;
        if(event.currentTarget.open)onSelect(current=>current.includes(source.id)?current:[...current,source.id]);
        else onSelect(current=>current.includes(source.id)?current.filter(id=>id!==source.id):current);
      }}>
        <summary><ChevronDown size={14} aria-hidden="true"/><span>{source.kind==='sql'?t("SQL check {number}",{number:referenceIds.includes(source.id)?referenceIds.indexOf(source.id)+1:source.number||index+1}):t(labels[source.kind])}{source.title?` · ${source.title}`:""}</span></summary>
        <div className="source-record-content">
          {source.repository&&<p className="text-xs break-all">{source.repository} · {source.commit}</p>}
          {source.line_start&&<p className="text-xs muted">{t("Lines {start}–{end}",{start:source.line_start,end:source.line_end||source.line_start})}</p>}
          {source.version&&<p className="text-xs muted">{t("Version")} {source.version}</p>}
          {safeLink(source.url)&&<a className="text-xs underline break-all" href={safeLink(source.url)} rel="noopener noreferrer" referrerPolicy="no-referrer">{source.kind==='document'?t("Download source document"):source.url}</a>}
          {(source.sql||source.excerpt)&&<SourceExcerpt source={source}/>}
          {typeof source.row_count==='number'&&<p className="text-xs muted">{t("Returned rows: {count}",{count:source.row_count})}{source.truncated?` · ${t("Result limited")}`:""}</p>}
          {source.note&&<p className="text-xs muted">{t(source.note)}</p>}
        </div>
      </details>)}
    </div>}
  </details>;
}
