"use client";

import { useEffect, useId, useRef, useState } from "react";
import { send, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function DeepAnalysisDialog({value,initialSubject,onUpdated,onClosed,onStarted,preparation}:{
  value:RequestDetail; initialSubject:string; onUpdated:(value:RequestDetail)=>void; onClosed:()=>void; onStarted?:()=>void;
  preparation?:{id:string;revision:number;discussion_revision:number};
}) {
  const {t}=useI18n();
  const dialog=useRef<HTMLDialogElement>(null);
  const prefix=useId();
  const [subject,setSubject]=useState(initialSubject);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{dialog.current?.showModal();},[]);
  return <dialog ref={dialog} className="publication-dialog" aria-labelledby={prefix+"-heading"} onClose={onClosed} onCancel={event=>{if(busy)event.preventDefault();}}>
    <h2 id={prefix+"-heading"}>{t("Deep analysis")}</h2>
    <p className="mt-2 text-sm muted">{t("Describe the need to investigate. SpecHelper will use relevant exchanges and sources from your environment.")}</p>
    <form className="mt-4 space-y-4" onSubmit={async event=>{
      event.preventDefault();if(busy)return;setBusy(true);setError("");
      try {
        onUpdated(await send<RequestDetail>(`/analyses/${value.id}/deep-analyze`,{
          expected_revision:preparation?.discussion_revision??value.discussion?.revision??0,
          intent:preparation?"change":"auto",subject,
          ...(preparation?{ticket_id:preparation.id,preparation_revision:preparation.revision}:{}),
        }));
        window.dispatchEvent(new Event("queue-updated"));dialog.current?.close();onStarted?.();
      } catch(failure){setError((failure as Error).message);}finally{setBusy(false);}
    }}>
      <div className="field"><label htmlFor={prefix+"-subject"}>{t("Need to analyze")}</label><Textarea id={prefix+"-subject"} rows={4} maxLength={30000} required disabled={busy} value={subject} onChange={event=>setSubject(event.target.value)}/></div>
      {error&&<p role="alert" className="text-sm text-red-700">{t(error)}</p>}
      <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={busy} onClick={()=>dialog.current?.close()}>{t("Cancel")}</Button><Button disabled={busy||!subject.trim()}>{t("Launch deep analysis")}</Button></div>
    </form>
  </dialog>;
}
