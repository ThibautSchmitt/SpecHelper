"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { APIError, send, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function NeedEditor({ value, onUpdated }: { value: RequestDetail; onUpdated: (value: RequestDetail) => void }) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value.need);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Keep the exact submission after a timeout; its operation id makes retries safe.
  const submission = useRef<{ text: string; payload: Record<string, unknown> } | null>(null);
  const canEdit = !value.validated_version && ["DRAFT", "DISCUSSING", "READY", "PARTIAL", "ERROR", "CANCELLED", "NEEDS_CLARIFICATION"].includes(value.status);

  return <div className="mt-4">
    {!editing ? <Button variant="outline" disabled={!canEdit} onClick={() => { setText(value.need); setEditing(true); }}>{t("Edit the need")}</Button> : <form className="space-y-3" onSubmit={async event => {
      event.preventDefault();
      setBusy(true); setError("");
      const need = text.trim();
      if (!submission.current || submission.current.text !== need) submission.current = { text: need, payload: {
        need, operation_id: crypto.randomUUID(), expected_revision: value.need_revision ?? 0,
        expected_version: value.latest_version?.number ?? null, expected_decision_revision: value.decision_revision ?? 0,
      } };
      try {
        const updated = await send<RequestDetail>(`/analyses/${value.id}/need`, submission.current.payload);
        onUpdated(updated); setEditing(false); submission.current = null;
      } catch (reason) {
        if (reason instanceof APIError && reason.status < 500) submission.current = null;
        setError((reason as Error).message);
      } finally { setBusy(false); }
    }}>
      <label className="block font-medium" htmlFor="revised-need">{t("Updated need")}</label>
      <Textarea id="revised-need" value={text} onChange={event => setText(event.target.value)} required maxLength={30000} disabled={busy} rows={5} />
      <p className="text-sm muted">{t(value.discussion?.enabled ? "Saving continues the discussion. Previous results keep their original scope until another deep analysis." : "Saving keeps the original need, decisions and previous results, then restarts the independent analysis. Previous conclusions remain out of date until reassessed.")}</p>
      {error && <p role="alert" className="text-sm text-destructive">{t(error)}</p>}
      <div className="flex flex-wrap justify-end gap-2" data-editor-actions>
        <Button type="button" variant="outline" disabled={busy} onClick={() => { setEditing(false); submission.current = null; setError(""); }}>{t("Cancel")}</Button>
        <Button disabled={busy || (!canEdit && !submission.current) || !text.trim() || (text.trim() === value.need && !submission.current)}>{t(busy ? "Saving…" : "Save")}</Button>
      </div>
    </form>}
  </div>;
}
