"use client";

import Link from "next/link";
import { WorkItemForm } from "@/components/work-item-form";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, CircleHelp, FileText, Plus, Search } from "lucide-react";
import { api, statuses, resultStates, type Environment, type RequestItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type AnalysisItem = RequestItem & {
  href: string;
  latest_activity_at: string;
  latest_version_number: number | null;
  has_result: boolean;
  intent_resolved: boolean;
};
type AnalysisPage = {
  items: AnalysisItem[];
  total: number;
  page: number;
  pages: number;
  has_previous: boolean;
  has_next: boolean;
};

const analysisStatuses = [
  "DRAFT", "QUEUED", "UNDERSTANDING", "NEEDS_CLARIFICATION", "ANALYZING",
  "REVIEWING", "GENERATING_RESULT", "CONTINUING_CONVERSATION", "GENERATING_TICKET",
  "READY", "PARTIAL", "ERROR", "CANCELLED",
];

export function AnalysesList() {
  const { t, dateLocale } = useI18n();
  const router = useRouter();
  const parameters = useSearchParams();
  const query = parameters.toString();
  const pendingQuery = useRef<string | null>(null);
  const navigationTargets = useRef(new Set<string>());
  const [text, setText] = useState(parameters.get("q") || "");
  const [data, setData] = useState<AnalysisPage | null>(null);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const workflow = parameters.get("workflow") || "all";

  useEffect(() => {
    // Merge rapid filter changes while a previous URL update is still pending.
    // An older completed navigation must not discard the user's newer filters.
    if (query === pendingQuery.current || !navigationTargets.current.has(query)) {
      pendingQuery.current = null;
      navigationTargets.current.clear();
    }
  }, [query]);

  useEffect(() => setText(new URLSearchParams(query).get("q") || ""), [query]);
  useEffect(() => {
    const controller = new AbortController();
    api<Environment[]>("/environments", { signal: controller.signal })
      .then(setEnvironments).catch(() => {});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    setLoading(true);
    setError("");
    api<AnalysisPage>(`/analyses?${query}`, { signal: controller.signal })
      .then((result) => { if (current) setData(result); })
      .catch((failure) => { if (current) setError(failure.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); };
  }, [query]);

  function navigate(changes: Record<string, string>, resetPage = true) {
    const next = new URLSearchParams(pendingQuery.current ?? query);
    for (const [key, value] of Object.entries(changes)) {
      if (value && value !== "all") next.set(key, value);
      else next.delete(key);
    }
    if (resetPage) next.delete("page");
    pendingQuery.current = next.toString();
    navigationTargets.current.add(next.toString());
    router.replace(`/analyses${next.size ? `?${next}` : ""}`, { scroll: false });
  }

  if (parameters.get("new") === "1" || parameters.has("from_question")) return <section className="space-y-5">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-semibold">{t("New analysis")}</h1>
      <Button asChild variant="outline"><Link href="/analyses">{t("All analyses")}</Link></Button>
    </header>
    <WorkItemForm unified embedded />
  </section>;

  return (
    <section className="analyses-page space-y-6" aria-labelledby="analyses-heading">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div><h1 id="analyses-heading" className="text-2xl font-semibold">{t("Analyses")}</h1>
          <p className="mt-1 text-sm muted">{t("Understand your project and prepare its next changes.")}</p></div>
        <Button asChild><Link href="/analyses?new=1"><Plus size={16} aria-hidden="true" />{t("New analysis")}</Link></Button>
      </header>
      <form className="analysis-filters flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); navigate({ q: text }); }}>
        <label className="min-w-48 flex-1 text-sm"><span className="sr-only">{t("Search analyses")}</span>
          <Input placeholder={t("Search analyses")} value={text} onChange={(event) => setText(event.target.value)} className="mt-1" maxLength={500} />
        </label>
        <label className="text-sm"><span className="sr-only">{t("Status")}</span>
          <select aria-label={t("Status")} className="mt-1 block h-10 rounded-md border bg-background px-3" value={parameters.get("status") || ""}
            onChange={(event) => navigate({ status: event.target.value, q: text })}>
            <option value="">{t("All statuses")}</option>
            {analysisStatuses.map((status) => <option key={status} value={status}>{t(statuses[status] || status)}</option>)}
          </select>
        </label>
        <label className="text-sm"><span className="sr-only">{t("Environment")}</span>
          <select aria-label={t("Environment")} className="mt-1 block h-10 max-w-full rounded-md border bg-background px-3" value={parameters.get("environment_id") || ""}
            onChange={(event) => navigate({ environment_id: event.target.value, q: text })}>
            <option value="">{t("All environments")}</option>
            {environments.map((environment) => <option key={environment.id} value={environment.id}>{environment.name}</option>)}
          </select>
        </label>
        <Button type="submit" variant="outline" aria-label={t("Search")} title={t("Search")} className="analysis-search-submit"><Search size={16} aria-hidden="true" /></Button>
      </form>
      <div className="flex flex-wrap gap-2" role="group" aria-label={t("Analysis type")}>
        {([ ["all", "All analyses"], ["question", "Questions"], ["request", "Changes"] ] as const).map(([value, label]) => (
          <Button key={value} variant={workflow === value ? "default" : "outline"} size="sm" aria-label={t(label)}
            aria-pressed={workflow === value} onClick={() => navigate({ workflow: value, q: text })}>{t(label)}{workflow === "all" && data && data.pages <= 1 && <span className="filter-count">({value === "all" ? data.total : data.items.filter(item => item.workflow === value).length})</span>}</Button>
        ))}
      </div>
      {error && <div role="alert"><p>{t("Analyses are unavailable. Try refreshing the page.")}</p><details className="mt-2 text-sm"><summary>{t("Diagnostics")}</summary><pre className="whitespace-pre-wrap break-words">{error}</pre></details></div>}
      <div aria-busy={loading} className="space-y-3">
        {loading && <p role="status" className="text-sm muted">{t("Loading analyses…")}</p>}
        {!loading && !error && !data?.items.length && <p className="rounded-lg border p-6 muted">{t("No analyses match these filters.")}</p>}
        {!loading && !error && data?.items.map((item) => {
          const Icon = item.workflow === "question" ? CircleHelp : FileText;
          const title = item.title || item.need.split("\n")[0];
          const prefix = title.replace(/…$/, "");
          const summary = (item.need.startsWith(prefix) ? item.need.slice(prefix.length) : item.need).replace(/^[\s.,:;!?-]+/, "").trim();
          return <Link key={item.id} href={item.href} data-business-state={item.result_state || item.status} className="analysis-row block rounded-lg border bg-card p-4 transition-colors hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
            <div className="flex items-start gap-3"><span className="analysis-row-icon"><Icon size={19} aria-hidden="true" /></span>
              <div className="min-w-0 flex-1"><div className="title-tags"><h2 className="line-clamp-2 break-words font-semibold" title={title}>{title}</h2>
                  <span className="badge analysis-state-pill" data-state={item.status}>{t(resultStates[item.result_state || ""] || statuses[item.status] || item.status)}</span>
                  <span className="badge analysis-intent-pill">{t(!item.intent_resolved ? "Analysis" : item.workflow === "question" ? "Question" : "Change")}</span>
                  <span className="badge analysis-environment-pill">{item.environment_name}</span>
                </div>
                {summary && <p className="mt-1 line-clamp-2 break-words text-sm muted">{summary}</p>}
                <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs muted">
                  <time dateTime={item.latest_activity_at}>{new Date(item.latest_activity_at).toLocaleString(dateLocale)}</time>
                  {item.latest_version_number !== null && <span>{t("Version")} {item.latest_version_number}</span>}
                </div>
              </div><ArrowRight size={16} className="shrink-0" aria-hidden="true" />
            </div>
          </Link>;
        })}
      </div>
      {!loading && !error && data && data.total > 0 && <nav className="flex flex-wrap items-center justify-between gap-3" aria-label={t("Analysis pagination")}>
        <p className="text-sm muted">{t("Page {page} of {pages} · {total} analyses", { page: data.page, pages: data.pages, total: data.total })}</p>
        <div className="flex gap-2"><Button variant="outline" disabled={!data.has_previous} onClick={() => navigate({ page: String(data.page-1) }, false)}>{t("Previous")}</Button>
          <Button variant="outline" disabled={!data.has_next} onClick={() => navigate({ page: String(data.page+1) }, false)}>{t("Next")}</Button></div>
      </nav>}
    </section>
  );
}
