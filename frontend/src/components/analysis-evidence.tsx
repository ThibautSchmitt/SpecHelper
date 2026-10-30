"use client";

import { AlertCircle, CheckCircle2, CircleHelp, Database, FileSearch, ShieldCheck } from "lucide-react";
import { Card } from "@/components/ui/card";
import { useI18n } from "@/lib/i18n";
import type { AnalysisClaim, ReliabilityReport, SQLReceipt, WebReceipt } from "@/lib/analysis-evidence";

const statusLabels = {
  supported: "Supported finding",
  partial: "Partially supported",
  contradicted: "Contradicted",
  unverified: "Not verified",
} as const;
const kindLabels = {
  observed: "Observed fact",
  interpretation: "Interpretation",
  contradiction: "Contradiction",
  unknown: "Unknown",
} as const;
const databaseLabels = {
  not_configured: "No business database is configured. Real records were not checked.",
  unavailable: "The business database could not be checked. Conclusions about real records remain unverified.",
  not_checked: "Business database records were not checked for this analysis.",
  checked: "Read-only database checks were completed within the scope shown below.",
} as const;
const exceptionLabels = {
  current_behavior: "Observed in the current behavior",
  historical_anomaly: "Historical inconsistency",
  unknown: "Interpretation remains unverified",
} as const;

function Receipt({ receipt }: { receipt: SQLReceipt }) {
  const { t, dateLocale } = useI18n();
  const date = new Date(receipt.checked_at);
  return <li className="min-w-0 rounded-md border p-3 text-xs space-y-2">
    <p className="break-words">{receipt.query_id} · {t(receipt.status === "checked" ? "Completed" : receipt.status === "rejected" ? "Rejected" : "Unavailable")}{!Number.isNaN(date.getTime()) && ` · ${date.toLocaleString(dateLocale)}`}</p>
    <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-muted/40 p-3">{receipt.sql}</pre>
    <p>{t("Returned rows: {count}", { count: receipt.row_count })}{receipt.truncated ? ` · ${t("Result limited")}` : ""}</p>
  </li>;
}

function Claim({ claim, checks, web }: { claim: AnalysisClaim; checks: SQLReceipt[]; web: WebReceipt[] }) {
  const { t } = useI18n();
  const translateNotes = (text: string) => text.split("\n").map(line => t(line)).join("\n");
  const Icon = claim.status === "supported" ? CheckCircle2 : claim.status === "unverified" ? CircleHelp : AlertCircle;
  return <article className="min-w-0 rounded-lg border p-4 sm:p-5 space-y-4" aria-label={claim.statement}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <h3 className="min-w-0 w-full break-words text-base leading-6 sm:w-auto sm:flex-1">{claim.statement}</h3>
      <span className="badge border"><Icon size={14} aria-hidden="true" />{t(statusLabels[claim.status])}</span>
    </div>
    <p className="text-xs muted">{t(kindLabels[claim.kind])} · {t(claim.basis === "official_rule" ? "Official rule" : claim.basis === "external_contract" ? "External contract" : "Deployment observation")}</p>
    <dl className="grid min-w-0 gap-3 text-sm sm:grid-cols-2">
      {[["Environment", claim.scope.environment], ["Period checked", claim.scope.period], ["Population checked", claim.scope.population], ["Sample limitations", claim.scope.sample_limits]].filter(([, value]) => !!value).map(([label, value]) => <div key={label} className="min-w-0"><dt className="font-medium muted">{t(label)}</dt><dd className="mt-1 whitespace-pre-wrap break-words leading-6">{value}</dd></div>)}
    </dl>
    {!!claim.scope.conditions.length && <div className="text-sm"><h4 className="font-medium">{t("Conditions checked")}</h4><ul className="mt-2 list-disc pl-5 space-y-1">{claim.scope.conditions.map((condition, index) => <li key={index} className="break-words">{condition}</li>)}</ul></div>}
    {!!claim.counterexamples.length && <section className="rounded-lg bg-muted/40 p-3 text-sm space-y-3" aria-label={t("Exceptions and counterexamples")}><h4 className="font-medium">{t("Exceptions and counterexamples")}</h4>{claim.counterexamples.map((example, index) => <div key={index}><p className="break-words leading-6">{example.description}</p><p className="mt-1 text-xs muted">{t(exceptionLabels[example.interpretation])}</p></div>)}</section>}
    {claim.verification_notes && <p className="whitespace-pre-wrap break-words text-sm leading-6">{translateNotes(claim.verification_notes)}</p>}
    {claim.universal && <p className="rounded-md border p-3 text-sm">{t("This statement covers all cases. The available checks establish only the scope described here.")}</p>}
    {!!claim.sources.length && <details className="min-w-0 rounded-lg border p-3">
      <summary className="cursor-pointer text-sm font-medium">{t("Sources and verification details")}</summary>
      <ul className="mt-3 min-w-0 space-y-3">{claim.sources.map((source, index) => source.kind === "git" ? <li key={index} className="min-w-0 rounded-md bg-muted/30 p-3 text-xs space-y-2"><p className="break-all">{source.repository} · {t("Commit")} {source.commit}</p><p className="break-all">{source.path}{source.symbol ? ` · ${source.symbol}` : ""} · {t("Lines {start}–{end}", { start: source.line_start, end: source.line_end })}</p><pre className="whitespace-pre-wrap break-words overflow-x-auto">{source.excerpt}</pre></li> : source.kind === "web" ? <li key={index} className="min-w-0 rounded-md border p-3 text-xs space-y-2">{(() => { const receipt = web.find(row => row.reference_id === source.reference_id); return receipt ? <><a className="text-primary underline break-all" href={receipt.url} target="_blank" rel="noreferrer noopener">{receipt.title}</a><p className="break-all">{receipt.url}</p><p>{t("Consulted on")}: {receipt.consulted_at}</p><p className="break-all">SHA-256: {receipt.sha256}</p></> : <p>{t("The external reference observation is unavailable.")}</p>; })()}<p>{source.authority}</p><p>{t("Reference applicability")}: {source.applicability_notes}</p><p>{[source.effective_date, source.version, source.jurisdiction, source.scope].filter(Boolean).join(" · ")}</p><blockquote className="whitespace-pre-wrap break-words">{source.excerpt}</blockquote></li> : <li key={index} className="min-w-0 text-xs"><p className="break-all">{t("Database check")} · {source.query_id}</p>{!checks.some(receipt => receipt.query_id === source.query_id) && <p className="mt-1 muted">{t("The database-check record is unavailable.")}</p>}</li>)}</ul>
      {checks.some(receipt => claim.sources.some(source => source.kind === "sql" && source.query_id === receipt.query_id)) && <ul className="mt-3 space-y-3">{checks.filter(receipt => claim.sources.some(source => source.kind === "sql" && source.query_id === receipt.query_id)).map(receipt => <Receipt key={receipt.query_id} receipt={receipt} />)}</ul>}
    </details>}
  </article>;
}

export function AnalysisEvidence({ report, historical = false }: { report?: ReliabilityReport | null; historical?: boolean }) {
  const { t } = useI18n();
  if (!report?.database || !Array.isArray(report.claims)) return null;
  const translateNotes = (text: string) => text.split("\n").map(line => t(line)).join("\n");
  return <Card className="space-y-5 min-w-0" aria-label={t("Analysis findings and limits")}>
    <div><h2 className="flex items-center gap-2"><ShieldCheck size={20} aria-hidden="true" />{t("Analysis findings and limits")}</h2><p className="mt-2 text-sm muted">{t(historical ? "These findings and limits belong to the displayed result version." : "The findings distinguish observed facts, interpretations and unresolved questions. Your confirmed business decisions are shown separately.")}</p></div>
    {report.blocking && <p role="status" className="flex items-start gap-2 rounded-lg border border-amber-500/50 p-4 text-sm"><AlertCircle size={18} className="shrink-0" aria-hidden="true" />{t("A material uncertainty remains. Resolve it before validating the business intent.")}</p>}
    <section className="min-w-0 rounded-lg bg-muted/40 p-4 space-y-2" aria-label={t("Business database verification")}><h3 className="flex items-center gap-2 text-sm"><Database size={16} aria-hidden="true" />{t("Business database verification")}</h3><p className="text-sm break-words">{t(databaseLabels[report.database.status])}</p>{report.database.scope && <p className="text-sm break-words">{report.database.scope}</p>}{report.database.limitations.map((limit, index) => <p key={index} className="text-sm muted break-words">{translateNotes(limit)}</p>)}{report.database.status === "checked" && <p className="text-sm muted">{t("Finding no counterexample in the queried records does not establish that no exception is possible.")}</p>}</section>
    {report.claims.length ? <div className="space-y-4">{report.claims.map(claim => <Claim key={claim.id} claim={claim} checks={report.database.checks} web={report.web_references || []} />)}</div> : <p className="text-sm muted">{t("No supported conclusion has been recorded yet.")}</p>}
    {!!report.limitations.length && <section className="text-sm"><h3 className="flex items-center gap-2"><FileSearch size={16} aria-hidden="true" />{t("Remaining verification limits")}</h3><ul className="mt-2 list-disc pl-5 space-y-2">{report.limitations.map((limit, index) => <li key={index} className="break-words">{translateNotes(limit)}</li>)}</ul></section>}
  </Card>;
}
