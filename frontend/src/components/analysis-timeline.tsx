"use client";

import Link from "next/link";
import { Card } from "@/components/ui/card";
import { type RequestDetail, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Event = { id: string; at: string; label: string; content: string; version?: number | null; state?: string; child?: string; url?: string };

export function AnalysisTimeline({ value }: { value: RequestDetail }) {
  const { t, dateLocale } = useI18n();
  const labels: Record<string, string> = {
    need: "Original need", need_revision: "Need updated", followup: "Follow-up",
    questions: "Clarification", clarification: "Clarification", answer: "Your answers", answers: "Your answers",
    understanding: "Understanding your need", error: "Analysis interrupted",
    decision_revision: "Decision updated",
    derived_request: "Linked change created",
  };
  const events: Event[] = (value.messages || []).filter(message => !["result", "decision_revision"].includes(message.kind)).map(message => ({
    id: `message-${message.id}`, at: message.created_at, label: labels[message.kind] || (message.role === "user" ? "You" : "SpecHelper"),
    content: message.content, version: message.version_number,
    child: typeof message.data?.child_id === "string" ? message.data.child_id : undefined,
  }));
  if (!value.messages?.some(message => message.kind === "need")) events.push({ id: "original", at: value.created_at,
    label: "Original need", content: value.original_need || value.need });
  for (const decision of value.decision_history || []) events.push({
    id: `decision-${decision.id}`, at: decision.created_at,
    label: decision.previous_id ? "Decision updated" : "Confirmed business decision",
    content: [decision.question.question, decision.value].filter(Boolean).join("\n"), version: decision.source_version,
  });
  for (const version of value.versions || []) events.push({
    id: `result-${version.number}`, at: version.created_at, label: "Result available", content: "",
    version: version.number, state: version.status,
  });
  for (const publication of value.publications || []) events.push({
    id: `publication-${publication.id}`, at: publication.created_at,
    label: publication.status === "PUBLISHED" ? "Ticket published" : publication.status === "ERROR" ? "Ticket publication failed" : "Ticket publication not confirmed",
    content: publication.title, version: publication.version_number,
    url: publication.status === "PUBLISHED" && /^https?:\/\//i.test(publication.url) ? publication.url : undefined,
  });
  events.sort((left, right) => new Date(left.at).getTime() - new Date(right.at).getTime() || left.id.localeCompare(right.id));

  return <Card aria-label={t("Analysis history")}>
    <h2>{t("Analysis history")}</h2>
    <ol className="mt-5 space-y-5 border-l pl-5">
      {events.map(event => <li key={event.id} className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm">{t(event.label)}</h3>
          <time dateTime={event.at} className="text-xs muted">{new Date(event.at).toLocaleString(dateLocale)}</time>
        </div>
        {event.content && <p className="whitespace-pre-wrap break-words text-sm leading-6">{event.label === "Analysis interrupted" ? t(event.content) : event.content}</p>}
        {event.child && <Link className="inline-block text-sm text-primary underline" href={`/analyses/${event.child}`}>{t("Open linked change")}</Link>}
        {event.url && <a className="mr-3 inline-block text-sm text-primary underline" href={event.url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{t("Open published ticket")}</a>}
        {event.version && <Link className="inline-block text-sm text-primary underline" href={`/analyses/${value.id}?version=${event.version}`}>
          {t("Version")} {event.version}{event.state ? ` · ${t(statuses[event.state] || event.state)}` : ""}
        </Link>}
      </li>)}
    </ol>
  </Card>;
}
