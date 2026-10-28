"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BookOpen, CircleHelp, Clock3 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api, statuses, resultStates, type RequestItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type HomeItem = RequestItem & { href: string; latest_activity_at: string };
type Overview = {
  sections: Record<"clarify" | "consult" | "active", { count: number; items: HomeItem[] }>;
  recent: HomeItem[];
};

export function AnalysisHome() {
  const { t } = useI18n();
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
  return <div className="space-y-7">
    <header><h1 className="text-2xl font-semibold">{t("Home")}</h1>
      <p className="mt-2 muted">{t("Ask a question, explore current behavior, or prepare a change.")}</p></header>
    <Button asChild><Link href="/analyses?new=1">{t("New analysis")}</Link></Button>
    {error && <p role="alert">{t(error)}</p>}
    {!overview && !error && <p role="status" className="text-sm muted">{t("Loading analyses…")}</p>}
    <section className="grid gap-4 md:grid-cols-3" aria-label={t("Analyses to resume")}>
      {([
        ["clarify", "Needs attention", CircleHelp],
        ["consult", "Results available", BookOpen],
        ["active", "In progress", Clock3],
      ] as const).map(([bucket, label, Icon]) => {
        const section = overview?.sections[bucket];
        return <div key={bucket} className="min-w-0 rounded-lg border bg-card p-4">
          <Link href={`/analyses?bucket=${bucket}`} className="flex items-center gap-2 font-semibold text-primary">
            <Icon size={18} aria-hidden="true" /><h2>{t(label)}</h2>
            {section && <span className="ml-auto text-sm">{section.count}</span>}
          </Link>
          {section && <ul className="mt-3 space-y-3">{section.items.map((item) => <li key={item.id}>
            <Link href={item.href} className="block min-w-0 rounded text-sm underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-primary">
              <span className="line-clamp-2 break-words" title={item.title || item.need}>{item.title || item.need}</span>
              <span className="mt-1 block text-xs muted">{t(resultStates[item.result_state || ""] || statuses[item.status] || item.status)}</span>
              {item.stage && <span className="mt-1 block line-clamp-2 text-xs muted">{t(item.stage)}</span>}
              {!!item.result_limits?.length && <span className="mt-1 block line-clamp-2 text-xs muted">{t(item.result_limits[0])}</span>}
              <span className="mt-1 block truncate text-xs muted">{item.environment_name}</span>
            </Link>
          </li>)}</ul>}
          {section?.count === 0 && <p className="mt-3 text-sm muted">{t("Nothing here for now.")}</p>}
        </div>;
      })}
    </section>

  </div>;
}
