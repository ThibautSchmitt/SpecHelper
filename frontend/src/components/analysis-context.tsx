"use client";

import { useI18n } from "@/lib/i18n";
import { roleLabels } from "@/lib/orchestration";
import type { ContextSnapshot, ContextUsage } from "@/lib/context";

const usageLabels = {
  observed: "Read observed",
  not_observed: "No read observed",
  unavailable: "Read telemetry unavailable",
};

export function AnalysisContext({ requestId, runNumber, snapshot, usage = [], workflow = "request" }: {
  requestId: string; runNumber?: number; snapshot?: ContextSnapshot; usage?: ContextUsage[]; workflow?: "request" | "question";
}) {
  const { t, dateLocale } = useI18n();
  if (!snapshot?.schema_version) return <p className="mt-3 text-xs muted">{t("Environment context was not recorded for this historical analysis.")}</p>;
  const resources = snapshot.resources || [];
  const factual = snapshot.analysis_protocol === "2.4" || snapshot.instructions?.mode === "factual";
  return <details className="mt-3 min-w-0 rounded-lg border p-3">
    <summary className="cursor-pointer text-sm font-medium">{t("Frozen analysis context")}</summary>
    <p className="mt-2 text-xs muted">{t("These document versions and instructions were frozen when this analysis started. Current environment changes do not affect them.")}</p>
    {snapshot.environment && <p className="mt-2 text-xs">{snapshot.environment.name} · {t("Context revision {number}", { number: snapshot.environment.revision })}</p>}
    {!!snapshot.official_references?.length && <section className="mt-3 text-sm"><h4 className="font-medium">{t("Official reference sources")}</h4><ul className="mt-2 space-y-2">{snapshot.official_references.map((reference, index) => <li key={index} className="break-words"><a className="text-primary underline" href={reference.url} target="_blank" rel="noreferrer noopener">{reference.url}</a>{reference.note && <p className="mt-1 muted">{reference.note}</p>}</li>)}</ul></section>}
    {snapshot.instructions && <details className="mt-3 text-sm">
      <summary className="cursor-pointer">{t(factual ? "Business terminology and factual context" : "Environment instructions")} · {snapshot.instructions.enabled ? t("Enabled") : t("Disabled")}</summary>
      <p className="mt-2 whitespace-pre-wrap break-words">{snapshot.instructions.text || t("No environment instructions.")}</p>
      <p className="mt-2 break-all text-xs muted">SHA-256: <code>{snapshot.instructions.sha256}</code></p>
    </details>}
    {snapshot.library && factual && <p className="mt-3 text-xs muted">{t("Skills are discovered globally for each step. Actual loads are recorded in assignment history.")}</p>}
    {snapshot.library && !factual && <section className="mt-4 text-sm">
      <h4 className="font-medium">{t("Frozen agent and skill versions")}</h4>
      <p className="mt-1 text-xs muted">{t("These definitions were available to this analysis. Later library changes do not replace them.")}</p>
      {(["agents", "skills"] as const).map(kind => <div key={kind} className="mt-3">
        <h5 className="text-xs font-medium">{t(kind === "agents" ? "Agents" : "Skills")}</h5>
        <ul className="mt-2 space-y-2">{(snapshot.library![kind] || []).map(item => <li key={`${item.slug}:${item.version}`}>
          <details className="rounded border p-2"><summary className="cursor-pointer break-words">{item.name} · v{item.version}</summary><p className="mt-2 whitespace-pre-wrap break-words text-xs">{item.instructions}</p></details>
        </li>)}</ul>
      </div>)}
    </section>}
    <h4 className="mt-3 text-sm font-medium">{t("Environment reference documents")}</h4>
    <p className="mt-1 text-xs muted">{t("Read status comes from runtime observations, not from an assistant’s claims. A missing observation does not prove that a file was unused.")}</p>
    {!resources.length && <p className="mt-2 text-sm muted">{t("No active reference documents in this snapshot.")}</p>}
    <ul className="mt-3 space-y-3">{resources.map(resource => {
      const observations = usage.filter(item => item.version_id === resource.version_id);
      return <li key={resource.version_id} className="min-w-0 rounded border p-3 text-sm">
        <p className="break-words font-medium">{resource.name}</p>
        <p className="mt-1 break-words text-xs muted">{resource.filename} · {t("Version")} {resource.version} · {resource.content_type} · {resource.size.toLocaleString(dateLocale)} {t("bytes")}</p>
        <p className="mt-1 break-all text-xs muted">SHA-256: <code>{resource.sha256}</code></p>
        {!resource.agent_readable && <p className="mt-2 text-xs text-amber-800">{t("This format is not readable by the agent. Replace it with a supported document.")}</p>}
        <ul className="mt-2 space-y-1 text-xs" aria-label={t("Document read observations")}>
          {observations.length ? observations.map((item, index) => <li key={index} className={item.status === "observed" ? "text-green-700" : "muted"}>{item.public_role && `${t(roleLabels[item.public_role] || item.public_role)} · `}{t(usageLabels[item.status] || usageLabels.unavailable)}</li>) : <li className="muted">{t("Read telemetry unavailable")}</li>}
        </ul>
        {runNumber !== undefined && <a className="mt-2 inline-block text-primary underline" href={`/api/${workflow === "question" ? "questions" : "requests"}/${requestId}/runs/${runNumber}/context/${resource.version_id}/download`}>{t("Download frozen document")}</a>}
      </li>;
    })}</ul>
  </details>;
}
