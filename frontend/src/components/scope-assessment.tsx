"use client";

import { useEffect, useId, useState } from "react";
import { CircleHelp, PencilLine } from "lucide-react";
import { api, send, type Environment, type RequestDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

export function ScopeAssessmentPanel({
  value,
  base,
  disabled = false,
  onUpdated,
}: {
  value: RequestDetail;
  base: "/questions" | "/requests";
  disabled?: boolean;
  onUpdated: (value: RequestDetail) => void;
}) {
  const { t } = useI18n();
  const elementId = useId();
  const assessment = value.scope_assessment!;
  const continuing = assessment.operation === "continue";
  const rejected = assessment.status === "OUT_OF_SCOPE";
  const [need, setNeed] = useState(continuing ? value.scope_pending_message || "" : value.need);
  const [clarification, setClarification] = useState(value.scope_clarification || "");
  const [environment, setEnvironment] = useState(String(value.environment_id || ""));
  const [editingRevision, setEditingRevision] = useState(value.scope_revision);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const stale = editingRevision !== undefined && value.scope_revision !== undefined && editingRevision !== value.scope_revision;
  useEffect(() => {
    if (continuing) return;
    let alive = true;
    api<Environment[]>("/environments")
      .then((items) => { if (alive) setEnvironments(items); })
      .catch((failure) => { if (alive) setError((failure as Error).message); });
    return () => { alive = false; };
  }, [continuing]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updated = await send<RequestDetail>(`${base}/${value.id}/scope`, {
        ...(rejected ? continuing ? { message: need } : { need } : {}),
        ...(continuing ? {} : { environment_id: environment ? Number(environment) : null }),
        clarification,
        ...(editingRevision !== undefined ? { expected_revision: editingRevision } : {}),
      });
      setEditingRevision(updated.scope_revision);
      onUpdated(updated);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return <Card aria-labelledby={`scope-heading-${elementId}`} data-scope-status={assessment.status}>
    <h2 id={`scope-heading-${elementId}`} className="flex items-center gap-2">
      {rejected ? <PencilLine size={18} aria-hidden="true" /> : <CircleHelp size={18} aria-hidden="true" />}
      {t(rejected ? "A project-related request is needed" : "Relate this to your project")}
    </h2>
    <p role="status" className="mt-3 text-sm leading-6">{t(assessment.message)}</p>
    <p className="mt-2 text-sm muted">{t(continuing ? "Your follow-up is saved. Its analysis has not started." : "Your text is saved. Analysis has not started for this request.")}</p>
    {continuing && !rejected && <div className="mt-4 rounded-lg bg-muted p-4">
      <h3 className="text-sm">{t("Your follow-up")}</h3>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{value.scope_pending_message}</p>
    </div>}
    <form onSubmit={submit} className="mt-5 space-y-4">
      {rejected ? <div className="field">
        <label htmlFor={`scope-need-${elementId}`}>{t(continuing ? "Reformulate your follow-up" : base === "/questions" ? "Reformulate your question" : "Reformulate your need")}</label>
        <Textarea id={`scope-need-${elementId}`} value={need} onChange={(event) => setNeed(event.target.value)} required minLength={1} maxLength={30000} disabled={busy || disabled} className="min-h-28" />
      </div> : <div className="field">
        <label htmlFor={`scope-reply-${elementId}`}>{t(assessment.question || "How does this relate to the selected project or its business context?")}</label>
        <Textarea id={`scope-reply-${elementId}`} value={clarification} onChange={(event) => setClarification(event.target.value)} required={!!value.environment_id || continuing} maxLength={3000} disabled={busy || disabled} className="min-h-24" aria-describedby={`scope-reply-help-${elementId}`} />
        <p id={`scope-reply-help-${elementId}`} className="mt-2 text-xs muted">{t("A short explanation of the link with the application is enough.")}</p>
      </div>}
      {!continuing && <div className="field">
        <label htmlFor={`scope-environment-${elementId}`}>{t("Environment")}</label>
        <select id={`scope-environment-${elementId}`} value={environment} onChange={(event) => setEnvironment(event.target.value)} disabled={busy || disabled}>
          <option value="">{t("Choose an environment")}</option>
          {environments.filter((item) => item.status === "READY").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </div>}
      {error && <p role="alert" className="text-sm text-red-700">{t(error)}</p>}
      {stale && <div role="status" className="rounded-lg border p-3 text-sm">
        <p>{t("This request changed in another browser. Reload its project context before saving.")}</p>
        <Button type="button" variant="outline" className="mt-3" disabled={busy || disabled} onClick={() => {
          setNeed(continuing ? value.scope_pending_message || "" : value.need);
          setClarification(value.scope_clarification || "");
          setEnvironment(String(value.environment_id || ""));
          setEditingRevision(value.scope_revision);
          setError("");
        }}>{t("Reload project context")}</Button>
      </div>}
      <Button disabled={busy || disabled || stale}>{t(busy ? "Checking project context…" : rejected ? "Save reformulation" : "Save project context")}</Button>
    </form>
  </Card>;
}
