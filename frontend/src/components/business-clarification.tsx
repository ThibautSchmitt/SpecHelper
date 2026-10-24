"use client";

import { useRef, useState } from "react";
import { AlertCircle, CheckCircle2, MessageCircle, Pencil, RotateCcw } from "lucide-react";
import { APIError, send, type RequestDetail, type ResultVersion } from "@/lib/api";
import type {
  BusinessDecision, BusinessOption, BusinessSummary, ClarificationQuestion, ConflictResponse,
} from "@/lib/business-decisions";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

const optionFields: [keyof BusinessOption, string][] = [
  ["relevance", "When this fits"], ["benefits", "Benefit"],
  ["limitations", "Limit"], ["consequences", "Business consequences"],
];

function getConflict(error: unknown): ConflictResponse | null {
  const details = error instanceof APIError ? error.details : null;
  if (!details || typeof details !== "object" || !("code" in details) || details.code !== "DECISION_CONFLICT" || !("conflicts" in details) || !Array.isArray(details.conflicts)) return null;
  return details as ConflictResponse;
}

function ConflictReview({ conflict, busy, onConfirm, onReview }: {
  conflict: ConflictResponse; busy: boolean; onConfirm: () => void; onReview: () => void;
}) {
  const { t } = useI18n();
  return <section className="mt-5 space-y-4 rounded-lg border border-primary/50 bg-muted/30 p-4" aria-label={t("Review a changed decision")}>
    <h3 className="flex items-center gap-2 text-sm"><AlertCircle size={18} aria-hidden="true" />{t("This changes a confirmed decision")}</h3>
    <p className="text-sm">{t("Your previous rule remains in effect until you confirm this change.")}</p>
    {conflict.conflicts.map(item => <div key={item.decision_id} className="space-y-3 text-sm">
      <p className="font-medium break-words">{item.proposed.question.question}</p>
      <dl className="grid min-w-0 gap-3 sm:grid-cols-2">
        <div className="min-w-0 rounded-md border bg-background p-3"><dt className="text-xs font-medium muted">{t("Current confirmed rule")}</dt><dd className="mt-2 whitespace-pre-wrap break-words">{item.previous.value}</dd></div>
        <div className="min-w-0 rounded-md border bg-background p-3"><dt className="text-xs font-medium muted">{t("Proposed new rule")}</dt><dd className="mt-2 whitespace-pre-wrap break-words">{item.proposed.value}</dd></div>
      </dl>
    </div>)}
    <div className="flex flex-wrap gap-2"><Button type="button" disabled={busy} onClick={onConfirm}>{t("Confirm the change")}</Button><Button type="button" variant="outline" disabled={busy} onClick={onReview}>{t("Review my choice")}</Button></div>
  </section>;
}

function QuestionFields({ question, selected, text, disabled, prefix, onSelect, onText }: {
  question: ClarificationQuestion; selected: string; text: string; disabled: boolean; prefix: string;
  onSelect: (value: string) => void; onText: (value: string) => void;
}) {
  const { t } = useI18n();
  const choices = question.kind === "choice" && !!question.options?.length;
  return <fieldset disabled={disabled} className="min-w-0 space-y-3" aria-describedby={question.reason ? `${prefix}-reason` : undefined}>
    <legend className="mb-3 text-base font-semibold break-words">{question.question}</legend>
    {question.reason && <p id={`${prefix}-reason`} className="text-sm muted break-words">{question.reason}</p>}
    {!!question.unknowns?.length && <div className="rounded-md bg-muted/50 p-3 text-sm"><p className="font-medium">{t("Still to verify")}</p><ul className="mt-2 list-disc space-y-1 pl-5">{question.unknowns.map((item, i) => <li key={i} className="break-words">{item}</li>)}</ul></div>}
    {choices ? <>
      <p className="text-sm muted">{t("These are possible business rules. Choose the one that fits your need, or describe another rule.")}</p>
      <div className="grid min-w-0 gap-3">
        {question.options!.map((option, index) => <label key={option.id} style={{ fontWeight: 400 }} className={`block min-w-0 cursor-pointer rounded-lg border bg-background p-4 transition-colors focus-within:ring-2 focus-within:ring-ring ${selected === option.id ? "border-primary bg-primary/5" : "hover:bg-muted/30"}`}>
          <span className="flex items-start gap-3"><input className="mt-1 shrink-0 accent-primary" type="radio" aria-label={`${String.fromCharCode(65 + index)} — ${option.label}`} name={`${prefix}-choice`} value={option.id} checked={selected === option.id} onChange={() => onSelect(option.id)} /><span className="min-w-0"><span className="font-medium break-words">{String.fromCharCode(65 + index)} — {option.label}</span>{selected === option.id && <span className="sr-only"> · {t("Selected")}</span>}</span></span>
          <p className="mt-3 text-sm leading-6 break-words">{option.behavior}</p>
          <dl className="mt-3 space-y-2 text-sm">{optionFields.map(([field, label]) => option[field] && <div key={field}><dt className="inline font-medium">{t(label)}: </dt><dd className="inline break-words">{option[field]}</dd></div>)}</dl>
        </label>)}
        <label style={{ fontWeight: 400 }} className={`block cursor-pointer rounded-lg border bg-background p-4 focus-within:ring-2 focus-within:ring-ring ${selected === "other" ? "border-primary bg-primary/5" : "hover:bg-muted/30"}`}><span className="flex items-center gap-3"><input type="radio" className="accent-primary" aria-label={`${String.fromCharCode(65 + question.options!.length)} — ${t("Other / clarify")}`} name={`${prefix}-choice`} value="other" checked={selected === "other"} onChange={() => onSelect("other")} /><span className="font-medium">{String.fromCharCode(65 + question.options!.length)} — {t("Other / clarify")}</span></span><span className="mt-2 block text-sm muted">{t("Neither option fits, or you want to add a different rule.")}</span></label>
      </div>
      {selected === "other" && <div className="field"><label htmlFor={`${prefix}-other`}>{t("Describe your alternative rule")}</label><Textarea id={`${prefix}-other`} required maxLength={10000} value={text} onChange={event => onText(event.target.value)} /><p className="mt-2 text-xs muted">{t("A description is required for Other.")}</p></div>}
    </> : <div className="field"><label className="sr-only" htmlFor={`${prefix}-answer`}>{question.question}</label><Textarea id={`${prefix}-answer`} required maxLength={10000} value={text} onChange={event => onText(event.target.value)} /></div>}
  </fieldset>;
}

export function BusinessClarification({ value, base, onUpdated }: {
  value: RequestDetail; base: string; onUpdated: (value: RequestDetail) => void;
}) {
  const { t } = useI18n();
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState<ConflictResponse | null>(null);
  const [pending, setPending] = useState<Record<string, unknown> | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const guided = value.questions.some(question => question.kind === "choice" && question.options?.length);
  function edit(update: () => void) { update(); setConflict(null); setPending(null); setError(""); }
  async function submit(payload: Record<string, unknown>) {
    setBusy(true); setError("");
    try { onUpdated(await send<RequestDetail>(`${base}/${value.id}/answers`, payload)); }
    catch (error) { const changed = getConflict(error); if (changed) { setConflict(changed); setPending(payload); } else { setError((error as Error).message); setConflict(null); } }
    finally { setBusy(false); }
  }
  return <Card className="border-primary/40" aria-label={t("Business clarification")}>
    <h2 className="flex items-center gap-2"><MessageCircle size={20} className="text-primary" aria-hidden="true" />{t("A few details before continuing")}</h2>
    <p className="mt-2 text-sm muted">{t(value.workflow === "question" ? "Your answers will help explain the relevant behavior." : "Your answers will help prepare a suitable proposal.")}</p>
    <form ref={form} noValidate className="mt-5 space-y-6" onSubmit={event => {
      event.preventDefault();
      const answers: Record<string, string> = {}, selected: Record<string, { option_id: string; text?: string }> = {};
      for (const question of value.questions) {
        if (question.kind === "choice" && question.options?.length) {
          if (!choices[question.id]) { setError("Choose an option or describe another rule for every question."); return; }
          if (choices[question.id] === "other" && !texts[question.id]?.trim()) { setError("Describe your alternative rule before continuing."); return; }
          selected[question.id] = { option_id: choices[question.id], ...(choices[question.id] === "other" ? { text: texts[question.id].trim() } : {}) };
        } else {
          if (!texts[question.id]?.trim()) { setError("Answer every question"); return; }
          answers[question.id] = texts[question.id].trim();
        }
      }
      submit({ answers, ...(Object.keys(selected).length ? { choices: selected } : {}), ...(value.decision_revision !== undefined ? { expected_decision_revision: value.decision_revision } : {}) });
    }}>
      {value.questions.map(question => <section key={question.id} className="min-w-0 rounded-lg border p-4 sm:p-5"><QuestionFields question={question} prefix={`clarify-${question.id}`} disabled={busy || !!conflict} selected={choices[question.id] || ""} text={texts[question.id] || ""} onSelect={selected => edit(() => setChoices({ ...choices, [question.id]: selected }))} onText={text => edit(() => setTexts({ ...texts, [question.id]: text }))} />{question.conflicts_with && value.decisions?.some(item => item.id === question.conflicts_with) && <p className="mt-3 text-sm muted">{t("This question revisits a confirmed decision. You will review any change before it takes effect.")}</p>}</section>)}
      {error && <p role="alert" className="text-sm break-words">{t(error)}</p>}
      {!conflict && <Button disabled={busy}>{busy ? t("Sending…") : t(guided ? "Validate and continue" : "Answer and continue")}</Button>}
    </form>
    {conflict && pending && <ConflictReview conflict={conflict} busy={busy} onConfirm={() => submit({ ...pending, confirm_changes: true })} onReview={() => { setConflict(null); setPending(null); setTimeout(() => form.current?.querySelector<HTMLInputElement | HTMLTextAreaElement>("input:checked, textarea")?.focus(), 0); }} />}
  </Card>;
}

export function BusinessOverview({ summary }: { summary?: BusinessSummary }) {
  const { t } = useI18n();
  if (!summary || ![summary.current, summary.desired, summary.gap, ...(summary.impacts || []), ...(summary.uncertainties || [])].some(Boolean)) return null;
  return <Card aria-label={t("Business overview")}>
    <h2>{t("Business overview")}</h2>
    <dl className="mt-4 grid min-w-0 gap-4 sm:grid-cols-2">{[["Current behavior", summary.current], ["Desired behavior", summary.desired], ["Gap to resolve", summary.gap]].filter(([, text]) => !!text).map(([label, text]) => <div key={label} className="min-w-0 rounded-lg bg-muted/40 p-4"><dt className="text-sm font-semibold">{t(label!)}</dt><dd className="mt-2 text-sm whitespace-pre-wrap break-words leading-6">{text}</dd></div>)}{!!summary.impacts?.length && <div className="min-w-0 rounded-lg bg-muted/40 p-4"><dt className="text-sm font-semibold">{t("Business impacts")}</dt><dd className="mt-2"><ul className="list-disc space-y-2 pl-4 text-sm">{summary.impacts.map((item, i) => <li key={i} className="break-words">{item}</li>)}</ul></dd></div>}</dl>
    {!!summary.uncertainties?.length && <section className="mt-4 rounded-lg border p-4"><h3 className="text-sm">{t("Still to verify")}</h3><ul className="mt-2 list-disc space-y-1 pl-4 text-sm">{summary.uncertainties.map((item, i) => <li key={i} className="break-words">{item}</li>)}</ul></section>}
  </Card>;
}

export function BusinessDecisions({ value, result, historical, base, onUpdated }: {
  value: RequestDetail; result?: ResultVersion | null; historical: boolean; base: string;
  onUpdated: (value: RequestDetail) => void;
}) {
  const { t, dateLocale } = useI18n();
  const [editing, setEditing] = useState<BusinessDecision | null>(null);
  const [selected, setSelected] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState<ConflictResponse | null>(null);
  const [pending, setPending] = useState<Record<string, unknown> | null>(null);
  const editor = useRef<HTMLFormElement>(null);
  const decisions = historical ? result?.decisions_snapshot || [] : value.decisions || [];
  const recorded = historical ? undefined : value.decision_history;
  const currentIds = (value.decisions || []).map(item => item.id).sort((a, b) => a - b);
  const resultIds = (result?.decisions_snapshot || []).map(item => item.id).sort((a, b) => a - b);
  const snapshotMatches = JSON.stringify(currentIds) === JSON.stringify(resultIds);
  const staleResult = !historical && !!result && !snapshotMatches;
  const enabled = !historical && !value.validated_version && ["READY", "PARTIAL", "ERROR", "NEEDS_CLARIFICATION"].includes(value.status);
  const evidenceBlocking = !!(value.evidence || result?.evidence)?.blocking;
  const canValidate = !historical && !evidenceBlocking && snapshotMatches && !!value.latest_version && value.status === "READY";
  if (value.decision_revision === undefined && result?.decisions_snapshot === undefined) return null;
  async function revise(payload: Record<string, unknown>) {
    if (!editing) return;
    setBusy(true); setError("");
    try { onUpdated(await send<RequestDetail>(`${base}/${value.id}/decisions/${editing.id}/revise`, payload)); setEditing(null); setConflict(null); setPending(null); }
    catch (error) { const changed = getConflict(error); if (changed) { setConflict(changed); setPending(payload); } else { setError((error as Error).message); setConflict(null); } }
    finally { setBusy(false); }
  }
  async function validate(reopen = false) {
    setBusy(true); setError("");
    try { onUpdated(await send<RequestDetail>(`${base}/${value.id}/validation`, { expected_version: value.latest_version!.number, expected_decision_revision: value.decision_revision }, reopen ? "DELETE" : "POST")); setEditing(null); }
    catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  return <Card className="space-y-5" aria-label={t("Confirmed business decisions")}>
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2>{t("Confirmed business decisions")}</h2><p className="mt-2 text-sm muted">{t(historical ? "These decisions belong to the displayed result version." : "Only your confirmed choices become business rules. Revising a rule starts a focused analysis.")}</p></div>{historical && <span className="badge">{t("Version")} {result?.number}</span>}</div>
    {staleResult && <p role="status" className="rounded-lg border border-primary/40 bg-muted/30 p-4 text-sm">{t("The displayed result still uses earlier decisions. A new analysis must reflect your latest choices before validation.")}</p>}
    {decisions.length ? <ol className="space-y-3">{decisions.map(item => <li key={item.id} className="rounded-lg border p-4 min-w-0"><div className="flex flex-col items-start justify-between gap-3 sm:flex-row"><div className="min-w-0 w-full flex-1"><h3 className="text-sm break-words">{item.question.question}</h3><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{item.value}</p><p className="mt-2 text-xs muted">{t("Decision {number}", { number: item.sequence })}{item.source_version ? ` · ${t("From result v{version}", { version: item.source_version })}` : ""}</p></div>{enabled && <Button variant="outline" size="sm" disabled={busy} onClick={() => { setEditing(item); setSelected(item.option_id || ""); setText(item.option_id === "other" || !item.option_id ? item.value : ""); setConflict(null); setPending(null); setError(""); }}><Pencil size={14} aria-hidden="true" />{t("Revise decision")}</Button>}</div></li>)}</ol> : <p className="text-sm muted">{t("No business decisions have been recorded for this version.")}</p>}
    {!!recorded?.length && <details className="rounded-lg border p-4"><summary className="cursor-pointer text-sm font-medium">{t("Decision history")}</summary><ol className="mt-4 space-y-4">{recorded.map(item => <li key={item.id} className="text-sm"><p className="font-medium break-words">{t("Decision {number}", { number: item.sequence })} · {item.question.question}</p><p className="mt-1 whitespace-pre-wrap break-words">{item.value}</p><p className="mt-1 text-xs muted">{new Date(item.created_at).toLocaleString(dateLocale)}{item.previous_id ? ` · ${t("Revises an earlier decision")}` : ""}{item.source_version ? ` · ${t("From result v{version}", { version: item.source_version })}` : ""}</p></li>)}</ol></details>}
    {error && <p role="alert" className="text-sm break-words">{t(error)}</p>}
    {editing && enabled && <form ref={editor} noValidate className="space-y-4 rounded-lg border border-primary/40 p-4" onSubmit={event => {
      event.preventDefault();
      if (editing.question.kind === "choice" && editing.question.options?.length && !selected) { setError("Choose an option or describe another rule for every question."); return; }
      if ((!editing.question.options?.length || selected === "other") && !text.trim()) { setError("Describe your alternative rule before continuing."); return; }
      revise({ expected_decision_revision: value.decision_revision, expected_version: value.latest_version?.number, ...(editing.question.kind === "choice" && editing.question.options?.length ? { option_id: selected, ...(selected === "other" ? { text: text.trim() } : {}) } : { text: text.trim() }) });
    }}>
      <QuestionFields question={editing.question} selected={selected} text={text} prefix={`revise-${editing.id}`} disabled={busy || !!conflict} onSelect={setSelected} onText={setText} />
      <p className="text-xs muted">{t("The current rule stays unchanged until you review and confirm the replacement.")}</p>
      {!conflict && <div className="flex flex-wrap gap-2"><Button disabled={busy}>{t("Review this change")}</Button><Button type="button" variant="outline" disabled={busy} onClick={() => setEditing(null)}>{t("Cancel")}</Button></div>}
    </form>}
    {conflict && pending && editing && enabled && <ConflictReview conflict={conflict} busy={busy} onConfirm={() => revise({ ...pending, confirm_change: true })} onReview={() => { setConflict(null); setPending(null); setTimeout(() => editor.current?.querySelector<HTMLInputElement | HTMLTextAreaElement>("input:checked, textarea")?.focus(), 0); }} />}
    {!historical && value.validated_version && <div role="status" className="space-y-3 rounded-lg border p-4"><p className="flex items-center gap-2 text-sm"><CheckCircle2 size={17} aria-hidden="true" />{t("Business intent validated for result v{version}.", { version: value.validated_version })}</p><p className="text-xs muted">{t("Reopen the request before changing a confirmed rule or continuing the discussion.")}</p>{canValidate && <Button variant="outline" disabled={busy} onClick={() => validate(true)}><RotateCcw size={15} aria-hidden="true" />{t("Reopen for changes")}</Button>}</div>}
    {canValidate && !value.validated_version && <div className="space-y-3 border-t pt-4"><p className="text-sm muted">{t("Does this result reflect your intended business behavior? Validation keeps the current decisions in place until you reopen the request.")}</p><Button disabled={busy} onClick={() => validate()}><CheckCircle2 size={16} aria-hidden="true" />{t("Validate business intent")}</Button></div>}
    {!historical && value.status === "PARTIAL" && !value.validated_version && <p className="text-sm muted">{t("Resolve the remaining blocking uncertainties before validating the business intent.")}</p>}
  </Card>;
}
