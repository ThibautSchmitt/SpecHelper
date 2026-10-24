"use client";

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

export function AnalysisRetryButton({ requestId, workflow = "request", title, onRetried }: { requestId: string; workflow?: "request" | "question"; title?: string; onRetried?: () => Promise<void> }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [queued, setQueued] = useState(false);
  return <div className="min-w-0">
    <Button type="button" variant="outline" size="sm" disabled={busy || queued} aria-label={title ? t("Resume analysis: {title}", { title }) : t("Resume analysis")} onClick={async () => {
      setBusy(true); setError("");
      try {
        await send(`/${workflow === "question" ? "questions" : "requests"}/${requestId}/retry`);
        setQueued(true);
        window.dispatchEvent(new Event("queue-updated"));
        await onRetried?.();
      } catch (error) { setError((error as Error).message); }
      finally { setBusy(false); }
    }}><RotateCcw size={13} aria-hidden="true" />{t(queued ? "Analysis queued" : busy ? "Resuming…" : "Resume analysis")}</Button>
    {error && <p role="alert" className="mt-2 text-xs text-red-700 break-words">{t(error)}</p>}
  </div>;
}
