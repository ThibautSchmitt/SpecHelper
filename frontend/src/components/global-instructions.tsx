"use client";

import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { OrchestrationSettings } from "@/components/orchestration-settings";

export function GlobalInstructionsForm() {
  const { t } = useI18n();
  const [loaded, setLoaded] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [review, setReview] = useState<NonNullable<OrchestrationSettings["migration_review"]>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let alive = true;
    api<OrchestrationSettings>("/orchestration-settings").then(config => {
      if (alive) { setLoaded(true); setInstructions(config.global_instructions || ""); setReview(config.migration_review || []); }
    }).catch(error => { if (alive) setError(error.message); });
    return () => { alive = false; };
  }, []);
  return <Card className="max-w-2xl space-y-4">
    <h2 className="flex items-center gap-2"><FileText size={20} aria-hidden="true" />{t("Global instructions")}</h2>
    <p className="text-sm muted">{t("Shared guidance applies to every assistant. Role missions and security rules remain mandatory; each connection can add its own specific instructions.")}</p>
    {!!review.length && <aside className="rounded-lg border border-amber-500/50 p-4 text-sm" aria-label={t("Legacy settings need review")}>
      <h3 className="font-medium">{t("Legacy settings need review")}</h3>
      <p className="mt-2 muted">{t("Some earlier settings were preserved without applying them automatically. Review them before adding shared guidance or activating skills.")}</p>
      <ul className="mt-3 list-disc space-y-2 pl-5">{review.map((item, index) => <li key={index} className="break-words">{item.slug && <span className="font-medium">{item.slug}: </span>}{t(item.reason)}</li>)}</ul>
    </aside>}
    {error && <p role="alert" className="text-sm text-red-700">{t(error)}</p>}
    {notice && <p role="status" className="text-sm">{t(notice)}</p>}
    <form onSubmit={async event => {
      event.preventDefault(); if (!loaded) return;
      setBusy(true); setError(""); setNotice("");
      try {
        const updated = await send<OrchestrationSettings>("/orchestration-settings", { global_instructions: instructions }, "PUT");
        setInstructions(updated.global_instructions || "");
        setReview(updated.migration_review || []);
        setNotice("Global instructions saved. Existing steps keep their recorded instructions.");
        window.dispatchEvent(new Event("orchestration-updated"));
      } catch (error) { setError((error as Error).message); }
      finally { setBusy(false); }
    }}>
      <fieldset disabled={busy || !loaded}>
        <label className="text-sm font-medium" htmlFor="global-instructions">{t("Global instructions")}</label>
        <Textarea id="global-instructions" className="mt-2" rows={6} maxLength={12000} value={instructions} onChange={event => setInstructions(event.target.value)} />
        <p className="mt-2 text-xs muted">{t("Environment documents provide factual context. They cannot replace these instructions or change analysis permissions.")}</p>
        <Button className="mt-4">{t("Save global instructions")}</Button>
      </fieldset>
    </form>
  </Card>;
}
