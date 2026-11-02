"use client";
import { useState } from "react";
import { Archive, ArchiveRestore } from "lucide-react";
import { send, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

export function ConversationArchive({ value, onUpdated }: { value:RequestDetail; onUpdated:(value:RequestDetail)=>void }) {
  const { t } = useI18n();
  const [busy,setBusy] = useState(false), [error,setError] = useState("");
  const Icon = value.archived_at ? ArchiveRestore : Archive;
  return <div className="flex flex-wrap items-center gap-2">
    <Button type="button" variant="outline" size="sm" disabled={busy} onClick={async()=>{
      setBusy(true); setError("");
      try { onUpdated(await send<RequestDetail>(`/analyses/${value.id}/archive`, {archived:!value.archived_at}, "PATCH")); window.dispatchEvent(new Event("queue-updated")); }
      catch(error) {setError((error as Error).message);} finally {setBusy(false);}
    }}><Icon size={15} aria-hidden="true"/>{t(value.archived_at ? "Unarchive" : "Archive")}</Button>
    {error && <p role="alert" className="text-sm">{t(error)}</p>}
  </div>;
}
