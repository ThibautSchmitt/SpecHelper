"use client";

import { useState } from "react";
import { Square } from "lucide-react";
import { send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

export function AnalysisCancelButton({ requestId, workflow = "request", title, onCancelled }: { requestId: string; workflow?: "request" | "question"; title?: string; onCancelled?: () => Promise<void> }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [cancelled, setCancelled] = useState(false);
  return <div className="min-w-0">
    <Button type="button" variant="ghost" size="sm" disabled={busy || cancelled} aria-label={title ? t("Cancel analysis: {title}", { title }) : t("Cancel analysis")} onClick={async () => {
      setBusy(true); setError("");
      try {
        await send(`/${workflow === "question" ? "questions" : "requests"}/${requestId}/cancel`);
        setCancelled(true);
        window.dispatchEvent(new Event("queue-updated"));
        await onCancelled?.();
      } catch (error) { setError((error as Error).message); }
      finally { setBusy(false); }
    }}><Square size={13} aria-hidden="true" />{t(cancelled ? "Cancelled" : busy ? "Cancelling…" : "Cancel analysis")}</Button>
    {error && <p role="alert" className="px-3 pb-2 text-xs text-red-700 break-words">{t(error)}</p>}
  </div>;
}
