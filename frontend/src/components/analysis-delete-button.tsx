"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function AnalysisDeleteButton({id, title, disabled}: {id:string; title:string; disabled:boolean}) {
  const {t}=useI18n();
  const router=useRouter();
  const dialog=useRef<HTMLDialogElement>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  async function remove() {
    setBusy(true);setError("");
    try {
      await send(`/analyses/${id}`,{confirmed:true},"DELETE");
      dialog.current?.close();
      window.dispatchEvent(new Event("queue-updated"));
      router.replace("/analyses");
      router.refresh();
    } catch(failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  return <>
    <Button variant="ghost" size="sm" disabled={disabled || busy} title={disabled ? t("Cancel the analysis and wait for its agents to stop before deleting it.") : t("Delete analysis")}
      onClick={()=>{setError("");dialog.current?.showModal();}}><Trash2 size={15} aria-hidden="true" />{t("Delete analysis")}</Button>
    <dialog ref={dialog} aria-label={t("Delete analysis")} aria-describedby={`delete-analysis-${id}`} onCancel={event=>{if(busy)event.preventDefault();}}
      className="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-lg overflow-auto rounded-xl border bg-card p-6 text-foreground shadow-xl backdrop:bg-black/40">
      <h2>{t("Delete analysis")}</h2>
      <p id={`delete-analysis-${id}`} className="mt-4 break-words text-sm">{t("Delete the analysis “{title}”?",{title})}</p>
      <p className="mt-3 text-sm muted">{t("It will be removed from Analyses, Home and Activity. Published tickets and their audit records are kept. This action cannot be undone in the application.")}</p>
      {error && <p role="alert" className="mt-3 text-sm">{t(error)}</p>}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="outline" disabled={busy} autoFocus onClick={()=>dialog.current?.close()}>{t("Cancel")}</Button>
        <Button disabled={disabled || busy} className="bg-[var(--danger)] text-white" onClick={remove}>{t(busy ? "Deleting…" : "Confirm deletion")}</Button>
      </div>
    </dialog>
  </>;
}
