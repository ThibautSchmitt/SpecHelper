"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { MarkdownReader } from "@/components/markdown-reader";

export function DeliverableViewer({url,title,label,beforeOpen,disabled=false}:{
  url:string; title:string; label?:string; beforeOpen?:()=>Promise<void>; disabled?:boolean;
}) {
  const {t}=useI18n();
  const dialog=useRef<HTMLDialogElement>(null);
  const [document,setDocument]=useState<{name:string;content:string}|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const generation=useRef(0);
  async function show() {
    const current=++generation.current;
    setLoading(true);setError("");setDocument(null);
    try {
      await beforeOpen?.();
      dialog.current?.showModal();
      const result=await api<{name:string;content:string}>(url);
      if(current===generation.current)setDocument(result);
    } catch(failure) {
      if(current===generation.current){dialog.current?.showModal();setError((failure as Error).message);}
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
      <div className="p-5">{loading?<p role="status">{t("Loading…")}</p>:error?<p role="alert">{t(error)}</p>:document&&<MarkdownReader>{document.content}</MarkdownReader>}</div>
      <footer className="ticket-modal-footer"><Button type="button" disabled={!document||loading} onClick={download}>{t("Download")} · .md</Button></footer>
    </dialog>
  </>;
}

export function AnalysisDeliverables({requestId,version}:{requestId:string;version:number}) {
  const base=`/analyses/${requestId}`;
  return <>
    <DeliverableViewer url={`${base}/versions/${version}/reports/business`} title="Business report" label="View business report"/>
    <DeliverableViewer url={`${base}/versions/${version}/reports/technical`} title="Technical report" label="View technical report"/>
    <DeliverableViewer url={`${base}/goal?source_version=${version}`} title="goal.md" label="Generate goal.md"/>
  </>;
}
