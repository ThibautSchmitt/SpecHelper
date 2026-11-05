"use client";

import { useRef, useState } from "react";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { MarkdownReader } from "@/components/markdown-reader";
import { ProviderLogo } from "@/components/provider-logo";

export function DeliverableViewer({url,title,label,beforeOpen,disabled=false,generate=false}:{
  url:string; title:string; label?:string; beforeOpen?:()=>Promise<void>; disabled?:boolean; generate?:boolean;
}) {
  const {t}=useI18n();
  const dialog=useRef<HTMLDialogElement>(null);
  const [document,setDocument]=useState<{name:string;content:string}|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [writers,setWriters]=useState<{connection_id:number;name:string;agent:string;model:string}[]>([]);
  const [writer,setWriter]=useState("");
  const generation=useRef(0);
  async function show(connectionId?:number) {
    const current=++generation.current;
    setLoading(true);setError("");setDocument(null);
    setWriters([]);
    try {
      await beforeOpen?.();
      dialog.current?.showModal();
      type Generation={name:string;content?:string;generation_id?:number;status?:string;error?:string};
      let result:Generation;
      if(generate){
        const endpoint=new URL(url,window.location.origin);
        endpoint.pathname+="/generate";
        if(connectionId)endpoint.searchParams.set("connection_id",String(connectionId));
        result=await send<Generation>(endpoint.pathname+endpoint.search,{});
        while(current===generation.current&&["QUEUED","RUNNING"].includes(result.status||"")){
          await new Promise(resolve=>setTimeout(resolve,1500));
          if(current!==generation.current)return;
          const check=new URL(url,window.location.origin);check.searchParams.set("generation_id",String(result.generation_id));
          result=await api<Generation>(check.pathname+check.search);
        }
        if(!result.content)throw new Error(result.error||"Goal generation interrupted. Try again.");
      }else result=await api<Generation>(url);
      if(current===generation.current)setDocument({name:result.name,content:result.content||""});
    } catch(failure) {
      if(current===generation.current){dialog.current?.showModal();setError((failure as Error).message);}
      if(generate&&current===generation.current){
        const options=new URL(url,window.location.origin);options.pathname+="/assistants";
        try{const items=await api<typeof writers>(options.pathname);if(current===generation.current){setWriters(items);setWriter(items[0]?String(items[0].connection_id):"");}}catch{/* Keep the original actionable error. */}
      }
    } finally {if(current===generation.current)setLoading(false);}
  }
  function download() {
    if(!document)return;
    const href=URL.createObjectURL(new Blob([document.content],{type:"text/markdown;charset=utf-8"}));
    const anchor=window.document.createElement("a");anchor.href=href;anchor.download=document.name;anchor.click();
    setTimeout(()=>URL.revokeObjectURL(href),1000);
  }
  return <>
    <Button type="button" variant="ghost" size="sm" disabled={disabled||loading} onClick={()=>void show()}>{t(label||title)}</Button>
    <dialog ref={dialog} className="ticket-preparation-modal" aria-label={t(title)} onClose={()=>{generation.current++;setLoading(false);}}>
      <header className="ticket-modal-header"><h2>{t(title)}</h2><Button type="button" variant="ghost" onClick={()=>dialog.current?.close()}>{t("Close")}</Button></header>
      <div className="p-5">{loading?<p role="status">{t(generate?"Preparing goal.md with AI…":"Loading…")}</p>:error?<div><p role="alert">{t(error)}</p>{writers.length>0?<div className="mt-4 space-y-3">
        <p className="text-sm muted">{t("Choose an AI to write this goal using the saved ticket and context. The conversation's AI stays unchanged.")}</p>
        <label className="block text-sm">{t("Writing assistant")}<select className="mt-1 w-full" value={writer} onChange={event=>setWriter(event.target.value)}>{writers.map(item=><option key={item.connection_id} value={item.connection_id}>{item.name} · {item.model}</option>)}</select></label>
        <Button type="button" onClick={()=>void show(Number(writer))}><ProviderLogo provider={writers.find(item=>String(item.connection_id)===writer)?.agent}/>{t("Write with the selected AI")}</Button>
      </div>:generate&&<Button type="button" variant="ghost" onClick={()=>void show()}>{t("Retry")}</Button>}</div>:document&&<MarkdownReader>{document.content}</MarkdownReader>}</div>
      <footer className="ticket-modal-footer"><Button type="button" disabled={!document||loading} onClick={download}>{t("Download")} · .md</Button></footer>
    </dialog>
  </>;
}

export function AnalysisDeliverables({requestId,version}:{requestId:string;version:number}) {
  const base=`/analyses/${requestId}`;
  return <>
    <DeliverableViewer url={`${base}/versions/${version}/reports/business`} title="Business report" label="View business report"/>
    <DeliverableViewer url={`${base}/versions/${version}/reports/technical`} title="Technical report" label="View technical report"/>
  </>;
}
