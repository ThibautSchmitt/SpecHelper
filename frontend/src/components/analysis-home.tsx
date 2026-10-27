"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, BookOpen, CircleHelp, Clock3 } from "lucide-react";
import { WorkItemForm } from "@/components/work-item-form";
import { api, statuses, resultStates, type RequestItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type HomeItem = RequestItem & { href: string; latest_activity_at: string };
type Overview = {
  sections: Record<"clarify" | "consult" | "active", { count: number; items: HomeItem[] }>;
  recent: HomeItem[];
};

export function AnalysisHome() {
  const { t, dateLocale } = useI18n();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    const refresh = () => api<Overview>("/analyses/overview", { signal: controller.signal })
      .then((value) => { if (current) { setOverview(value); setError(""); } })
      .catch((failure) => { if (current) setError(failure.message); });
    refresh();
    const timer = window.setInterval(refresh, 15000);
    return () => { current = false; controller.abort(); window.clearInterval(timer); };
  }, []);
  return <div className="space-y-7">
    <header><h1 className="text-2xl font-semibold">{t("Home")}</h1>
      <p className="mt-2 muted">{t("Ask a question, explore current behavior, or prepare a change.")}</p></header>
    <WorkItemForm unified embedded />
    {error && <p role="alert">{t(error)}</p>}
    {!overview && !error && <p role="status" className="text-sm muted">{t("Loading analyses…")}</p>}
    <section className="grid gap-4 md:grid-cols-3" aria-label={t("Analyses to resume")}>
      {([
        ["clarify", "To clarify", CircleHelp],
        ["consult", "Ready to read", BookOpen],
        ["active", "In progress", Clock3],
      ] as const).map(([bucket, label, Icon]) => {
        const section = overview?.sections[bucket];
        return <div key={bucket} className="min-w-0 rounded-lg border bg-card p-4">
          <Link href={`/analyses?bucket=${bucket}`} className="flex items-center gap-2 font-semibold text-primary">
            <Icon size={18} aria-hidden="true" /><h2>{t(label)}</h2>
            {section && <span className="ml-auto text-sm">{section.count}</span>}
          </Link>
          {section && <ul className="mt-3 space-y-3">{section.items.map((item) => <li key={item.id}>
            <Link href={item.href} className="block truncate text-sm underline-offset-4 hover:underline" title={item.title || item.need}>
              {item.title || item.need}</Link>
            <p className="truncate text-xs muted">{item.environment_name} · {t(resultStates[item.result_state || ""] || statuses[item.status] || item.status)}</p>
          </li>)}</ul>}
          {section?.count === 0 && <p className="mt-3 text-sm muted">{t("Nothing here for now.")}</p>}
        </div>;
      })}
    </section>
    {overview && <section aria-labelledby="recent-analyses-heading" className="rounded-lg border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="recent-analyses-heading" className="font-semibold">{t("Recent analyses")}</h2>
        <Link href="/analyses" className="inline-flex items-center gap-2 text-sm text-primary">{t("All analyses")}<ArrowRight size={14} aria-hidden="true" /></Link></div>
      {overview.recent.length ? <ul className="mt-4 divide-y">{overview.recent.map((item) => <li key={item.id}>
        <Link href={item.href} className="flex min-w-0 flex-wrap items-center gap-3 py-3">
          <div className="min-w-0 flex-1"><h3 className="truncate font-medium" title={item.title || item.need}>{item.title || item.need}</h3>
            <p className="mt-1 text-xs muted">{item.environment_name} · <time dateTime={item.latest_activity_at}>{new Date(item.latest_activity_at).toLocaleString(dateLocale)}</time></p></div>
          <span className="text-xs muted">{t(resultStates[item.result_state || ""] || statuses[item.status] || item.status)}</span><ArrowRight size={15} aria-hidden="true" /></Link>
      </li>)}</ul> : <p className="mt-4 text-sm muted">{t("Your analyses will appear here.")}</p>}
    </section>}
  </div>;
}
