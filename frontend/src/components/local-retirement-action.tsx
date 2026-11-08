"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function LocalRetirementAction({url, analysis=false, onRemoved}: {url:string; analysis?:boolean; onRemoved:()=>void}) {
  const {t}=useI18n();
  const dialog=useRef<HTMLDialogElement>(null);
  const [busy,setBusy]=useState(false);
  const [pending,setPending]=useState(false);
  const [error,setError]=useState("");
  const title=analysis?"Delete deep analysis":"Remove from SpecHelper";
  async function remove() {
    setBusy(true);setError("");
    try {
      const result=await send<{status:string}>(url,{confirmed:true},"DELETE");
      if(result.status==="STOPPING"){setPending(true);return;}
      setPending(false);dialog.current?.close();
      window.dispatchEvent(new Event("queue-updated"));onRemoved();
    } catch(failure){setPending(false);setError((failure as Error).message);}
    finally{setBusy(false);}
  }
  const retry=useRef(remove);
  retry.current=remove;
  useEffect(()=>{
    if(!pending||busy)return;
    const timer=setTimeout(()=>retry.current(),2000);
    return()=>clearTimeout(timer);
  },[pending,busy,url]);
  return <>
    <details className="action-menu w-fit">
      <summary aria-label={t(analysis?"Analysis actions":"Ticket actions")}>⋯</summary>
      <div className="action-menu-items"><button type="button" onClick={event=>{event.currentTarget.closest("details")?.removeAttribute("open");setError("");dialog.current?.showModal();}}>{t(title)}</button></div>
    </details>
    <dialog ref={dialog} aria-label={t(title)} onCancel={event=>{if(busy)event.preventDefault();}}
      className="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-lg overflow-auto rounded-xl border bg-card p-6 text-foreground shadow-xl backdrop:bg-black/40">
      <h2>{t(title)}</h2>
      <p className="mt-4 text-sm">{t(analysis?"Delete this analysis and its results? This action cannot be undone.":"Remove this ticket from SpecHelper? It will remain available on its external platform.")}</p>
      {pending&&<p role="status" className="mt-3 text-sm muted">{t("Stopping agents and releasing their sessions…")}</p>}
      {error&&<p role="alert" className="mt-3 text-sm">{t(error)}</p>}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="outline" autoFocus disabled={busy} onClick={()=>dialog.current?.close()}>{t(pending?"Close":"Cancel")}</Button>
        <Button disabled={busy||pending} className="bg-[var(--danger)] text-white" onClick={remove}>{t("Confirm deletion")}</Button>
      </div>
    </dialog>
  </>;
}
