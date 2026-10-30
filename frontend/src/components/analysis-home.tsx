"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BookOpen, CircleHelp, Clock3, Flame, ArrowRight, ClipboardList, Sparkles } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api, statuses, resultStates, type RequestItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useInstanceName } from "@/lib/instance";

type HomeItem = RequestItem & { href: string; latest_activity_at: string };
type Overview = {
  sections: Record<"clarify" | "consult" | "active", { count: number; items: HomeItem[] }>;
  recent: HomeItem[];
};

export function AnalysisHome() {
  const { t, dateLocale } = useI18n();
  const instanceName = useInstanceName();
  const [query, setQuery] = useState("");
  const [launchError, setLaunchError] = useState(false);
  const router = useRouter();
  const parameters = useSearchParams();
  const legacyCreation = parameters.has("new") || parameters.has("from_question");
  useEffect(() => {
    if (legacyCreation) {
      const next = new URLSearchParams(parameters.toString());
      next.set("new", "1");
      router.replace(`/analyses?${next}`);
    }
  }, [legacyCreation, parameters, router]);
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
  return <div className="analysis-home space-y-6">
    <header className="home-hero">
      <div className="home-hero-copy">
        <h1 className="flex items-center gap-3"><Sparkles size={28} className="shrink-0" aria-hidden="true" />{instanceName}</h1>
      </div>
      <form className="home-launch" onSubmit={event => { event.preventDefault(); setLaunchError(false); try { sessionStorage.setItem("spechelper-home-draft", query); router.push("/analyses?new=1&from_home=1"); } catch { setLaunchError(true); } }}>
        <CircleHelp size={18} aria-hidden="true" /><label className="sr-only" htmlFor="home-analysis-idea">{t("A question about your project")}</label>
        <input id="home-analysis-idea" value={query} maxLength={30000} onChange={event => setQuery(event.target.value)} placeholder={t("A question about your code, an analysis, a change…")} />
        <Button type="submit" size="sm" className="aspect-square px-2" aria-label={t("New analysis")}><ArrowRight size={18} aria-hidden="true" /></Button>
      </form>
    </header>
    {launchError && <p role="alert">{t("The draft could not be saved. Copy your text before opening a new analysis.")}</p>}
    {error && <div role="alert"><p>{t("Analyses are unavailable. Try refreshing the page.")}</p><details className="mt-2 text-sm"><summary>{t("Diagnostics")}</summary><pre className="whitespace-pre-wrap break-words">{error}</pre></details></div>}
    {!overview && !error && <p role="status" className="text-sm muted">{t("Loading analyses…")}</p>}
    <section className="grid gap-4 md:grid-cols-3" aria-label={t("Analyses to resume")}>
      {([
        ["clarify", "Needs attention", Flame],
        ["active", "In progress", Clock3],
        ["consult", "Results available", BookOpen],
      ] as const).map(([bucket, label, Icon]) => {
        const section = overview?.sections[bucket];
        return <div key={bucket} className="home-bucket min-w-0 rounded-lg border bg-card p-4" data-bucket={bucket}>
          <Link href={`/analyses?bucket=${bucket}`} className="flex items-center gap-2 font-semibold text-primary">
            <Icon size={18} aria-hidden="true" /><h2>{t(label)}</h2>
            {section && <span className="ml-auto text-sm">{section.count}</span>}
          </Link>
          {section && <ul className="mt-3 space-y-3">{section.items.map((item) => <li key={item.id} className="home-result">
            <Link href={item.href} className="block min-w-0 rounded text-sm underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-primary">
              <span className="title-tags"><span className="title-text line-clamp-2 break-words" title={item.title || item.need}>{item.title || item.need}</span>
                <span className="badge" data-state={item.status}>{t(resultStates[item.result_state || ""] || statuses[item.status] || item.status)}</span>
              </span>
              {item.stage && <span className="mt-1 block line-clamp-2 text-xs muted">{t(item.stage)}</span>}
              <span className="mt-1 block truncate text-xs muted">{item.environment_name}</span><time className="home-item-date" dateTime={item.latest_activity_at}>{new Date(item.latest_activity_at).toLocaleDateString(dateLocale, { day: "numeric", month: "short" })}</time>
            </Link>
          </li>)}</ul>}
          {section?.count === 0 && <div className="home-empty"><ClipboardList size={52} strokeWidth={1} aria-hidden="true" /><p>{t(bucket === "active" ? "No items in progress" : "Nothing here for now.")}</p><p className="text-xs muted">{t(bucket === "active" ? "Running analyses will appear here." : "Nothing here for now.")}</p></div>}
          {!!section?.count && <Link href={`/analyses?bucket=${bucket}`} className="mt-4 inline-block rounded text-xs text-primary underline focus-visible:outline-2 focus-visible:outline-primary">{t(bucket === "consult" ? "View all results" : "View all items")} <ArrowRight size={14} aria-hidden="true" /></Link>}
        </div>;
      })}
    </section>

  </div>;
}
