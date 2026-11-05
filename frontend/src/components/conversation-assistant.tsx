"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ProviderLogo } from "@/components/provider-logo";
import { api, send, type ConversationAssistant, type RequestDetail } from "@/lib/api";
import { assistantName } from "@/lib/assistant-providers";
import { useI18n } from "@/lib/i18n";
import { ConnectionAvailability } from "@/components/connection-availability";

type Choice = Omit<ConversationAssistant, "availability"> & {configuration_token:string};
type Options = {revision:number; can_continue:boolean; options:Choice[]};

export function ConversationAssistantControl({value,onUpdated}:{value:RequestDetail;onUpdated:(value:RequestDetail)=>void}) {
  const {t}=useI18n();
  const current=value.discussion?.assistant;
  const [options,setOptions]=useState<Options|null>(null);
  const [selected,setSelected]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  if(!current)return null;
  const exhausted=current.availability === "QUOTA_EXHAUSTED";
  const unavailable=current.continuation_reason === "connection_unavailable";
  const unauthorized=current.continuation_reason === "analyst_role_removed";
  const previous=value.discussion?.assistant_history?.filter(item=>!item.current) || [];
  const canChoose=(exhausted || unavailable || unauthorized) && !value.archived_at && value.discussion?.mode === "discussion" && value.discussion.job?.status !== "RUNNING";
  const model=(item:Pick<ConversationAssistant,"agent"|"model"|"reasoning_effort">)=>`${item.model || t("Provider default model")}${item.agent !== "antigravity" && item.reasoning_effort ? ` ${item.reasoning_effort}` : ""}`;
  async function load() {
    setBusy(true);setError("");setSelected("");
    try {setOptions(await api<Options>(`/analyses/${value.id}/discussion/continuation-options`));}
    catch(failure){setError((failure as Error).message);}
    finally{setBusy(false);}
  }
  async function resume() {
    const target=options?.options.find(item=>String(item.connection_id)===selected);
    if(!target || !options)return;
    setBusy(true);setError("");
    try {
      const updated=await send<RequestDetail>(`/analyses/${value.id}/discussion/continue-with`,{
        expected_revision:options.revision, connection_id:target.connection_id,
        configuration_token:target.configuration_token,
      });
      onUpdated(updated);setOptions(null);setSelected("");
      window.dispatchEvent(new Event("queue-updated"));
    } catch(failure){setError((failure as Error).message);}
    finally{setBusy(false);}
  }
  return <div className="mt-3 max-w-full space-y-2" aria-label={t("Conversation assistant")}>
    <div className="connection-tags text-sm">
      {!!previous.length && <span className="text-xs muted">{t("Current assistant")}</span>}
      <ProviderLogo provider={current.agent} />
      <span className="min-w-0 max-w-full break-words">{current.name || assistantName(current.agent)}</span>
      <span className="badge connection-tag connection-model-tag" title={`${t("Model")}: ${current.model || t("Provider default model")}${current.reasoning_effort ? ` · ${t("Reasoning effort")}: ${current.reasoning_effort}` : ""}`}>{model(current)}</span>
      {exhausted && <ConnectionAvailability connection={current} />}
      {canChoose && <Button type="button" variant="ghost" size="sm" disabled={busy} aria-expanded={!!options} onClick={()=>options?setOptions(null):void load()}>{t("Continue the analysis with…")}</Button>}
    </div>
    {!!previous.length && <div aria-label={t("AI history")} className="space-y-1 text-xs">
      <span className="muted">{t("AI history")}</span>
      <ol className="flex flex-wrap items-center gap-x-4 gap-y-2">{previous.map((item,index)=><li key={`${item.connection_id}-${index}`} className="connection-tags" title={t(item.used ? "Response received" : "Previously selected")}>
        <ProviderLogo provider={item.agent} />
        <span className="muted break-words">{item.name || assistantName(item.agent)}</span>
        <span className="badge connection-tag connection-model-tag">{model(item)}</span>
      </li>)}</ol>
    </div>}
    {(unauthorized || unavailable) && <p className="text-xs muted">{t(unauthorized ? "The selected assistant no longer has the Analyst role. Choose another assistant to continue." : "The selected AI connection is no longer available. Choose another assistant to continue.")}</p>}
    {error && <p role="alert" className="text-sm text-red-700">{t(error)}</p>}
    {options && canChoose && <div className="space-y-2">
      <p className="text-xs muted">{t("A new session will receive the recorded history and project context. Its model and reasoning may interpret them differently.")}</p>
      {!options.can_continue ? <p className="text-sm muted">{t("The current assistant can continue again. Refresh the conversation.")}</p> : !options.options.length ? <p className="text-sm muted">{t("No other assistant with the Analyst role is currently available.")}</p> :
        <form className="flex flex-wrap items-end gap-2" onSubmit={event=>{event.preventDefault();void resume();}}>
          <div className="field min-w-0 max-w-full flex-1"><label htmlFor="continuation-assistant">{t("Available assistant")}</label>
            <select id="continuation-assistant" disabled={busy} value={selected} onChange={event=>setSelected(event.target.value)}>
              <option value="">{t("Choose an available assistant")}</option>
              {options.options.map(item=><option key={item.connection_id} value={String(item.connection_id)}>{item.name} · {model(item)}</option>)}
            </select>
          </div>
          <Button disabled={busy || !selected}>{t("Continue")}</Button>
          <Button type="button" variant="ghost" disabled={busy} onClick={()=>{setOptions(null);setSelected("");}}>{t("Cancel")}</Button>
        </form>}
    </div>}
  </div>;
}
