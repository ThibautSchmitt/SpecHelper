"use client";
import Link from "next/link";
import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { ChevronDown } from "lucide-react";
import { AnalysisCancelButton } from "@/components/analysis-cancel-button";
import { api, resultStates } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { AnalysisWarning } from "@/lib/orchestration";

export type QueueJob = {
  id: number | string;
  kind: string;
  workflow?: "request" | "question";
  status: string;
  queue_state?: string;
  activity_key?: string;
  requires_attention?: boolean;
  stage?: string;
  stage_number?: number;
  stage_count?: number;
  elapsed_seconds?: number;
  active_analysis_seconds?: number | null;
  clarification_since?: string | null;
  queued_since?: string | null;
  analysis_state?: string;
  request_id?: string | null;
  can_cancel?: boolean;
  can_retry?: boolean;
  pause_reason?: string;
  waiting_reason?: string;
  assignment_state?: "current" | "previous" | "unassigned";
  executor_name?: string | null;
  publication_status?: string;
  title: string;
  environment_name: string;
  operation: string;
  agent: string | null;
  connection_name?: string | null;
  model?: string | null;
  public_role?: string;
  warnings?: AnalysisWarning[];
  assignments?: {
    connection_id: number;
    connection_name: string;
    agent: string;
    model: string;
    public_role?: string;
    model_family?: string;
  }[];
  request_status: string;
  result_status?: "complete" | "partial" | "unusable" | "pending";
  result_limits?: string[];
  queue_position: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string;
  href: string;
};

const QueueContext = createContext<{
  jobs: QueueJob[];
  error: string;
  now: number;
  loading: boolean;
}>({ jobs: [], error: "", now: 0, loading: true });

function stateOf(job: QueueJob) {
  return job.queue_state || (job.request_status === "NEEDS_CLARIFICATION" && job.status === "DONE" ? "PAUSED" : job.status);
}

function queueCards(jobs: QueueJob[]) {
  const latest = new Map<string, QueueJob>();
  for (const job of jobs) {
    const key = job.activity_key || (job.kind === "analysis" && job.request_id ? `analysis:${job.request_id}` : `${job.kind}:${job.id}`);
    const previous = latest.get(key);
    if (!previous || Date.parse(job.created_at) > Date.parse(previous.created_at) || (job.created_at === previous.created_at && Number(job.id) > Number(previous.id))) latest.set(key, job);
  }
  return Array.from(latest.values()).filter(job => !(job.kind === "sync" && stateOf(job) === "DONE"));
}

export function useQueueAttention() {
  const { jobs, error } = useContext(QueueContext);
  const cards = queueCards(jobs);
  return { count: cards.filter(job => job.requires_attention ?? (stateOf(job) === "PAUSED" || (stateOf(job) === "ERROR" && !!(job.href || job.request_id || job.can_retry)))).length,
    clarifications: cards.filter(job => !!job.request_id && stateOf(job) === "PAUSED" && job.analysis_state !== "scope_rejected").length,
    running: cards.filter(job => ["RUNNING", "QUEUED", "WAITING_AI"].includes(stateOf(job))).length,
    error: !!error };

}

function waitingDuration(since: string | null | undefined, now: number) {
  const seconds = since ? Math.max(0, Math.floor((now - Date.parse(since)) / 1000)) : NaN;
  if (!Number.isFinite(seconds)) return null;
  return seconds >= 3600 ? `${Math.floor(seconds / 3600)} h` : seconds >= 60 ? `${Math.floor(seconds / 60)} min` : `${seconds} s`;
}
export function TaskQueueProvider({ children }: { children: React.ReactNode }) {
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    let alive = true;
    const update = () =>
      api<QueueJob[]>("/queue")
        .then((value) => {
          if (alive) {
            setJobs(value);
            setLoading(false);
            setError("");
            setNow(Date.now());
          }
        })
        .catch((e) => {
          if (alive) {
            setError(e.message);
            setLoading(false);
          }
        });
    update();
    const timer = setInterval(update, 3000);
    window.addEventListener("queue-updated", update);
    return () => {
      alive = false;
      clearInterval(timer);
      window.removeEventListener("queue-updated", update);
    };
  }, []);
  return (
    <QueueContext.Provider value={{ jobs, error, now, loading }}>
      {children}
    </QueueContext.Provider>
  );
}

export function TaskQueue() {
  const { t } = useI18n();
  const { jobs, error, now, loading } = useContext(QueueContext);
  const [showCompleted, setShowCompleted] = useState(false);
  const list = useRef<HTMLOListElement>(null);
  const positions = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const next = new Map<string, number>();
    for (const element of Array.from(
      list.current?.querySelectorAll<HTMLElement>("[data-job]") || [],
    ) as HTMLElement[]) {
      const key = element.dataset.job!;
      const top = element.getBoundingClientRect().top;
      const previous = positions.current.get(key);
      next.set(key, top);
      if (
        previous !== undefined &&
        previous !== top &&
        !window.matchMedia("(prefers-reduced-motion: reduce)").matches
      )
        element.animate(
          [
            { transform: `translateY(${previous - top}px)` },
            { transform: "translateY(0)" },
          ],
          { duration: 250, easing: "ease-out" },
        );
    }
    positions.current = next;
  }, [jobs]);
  const cards = queueCards(jobs);
  const order = ["PAUSED", "ERROR", "RUNNING", "WAITING_AI", "QUEUED", "CANCELLED", "DONE"];
  const completed = cards.filter(job => ["DONE", "CANCELLED"].includes(stateOf(job)))
    .sort((a, b) => Date.parse(b.finished_at || b.created_at) - Date.parse(a.finished_at || a.created_at)).slice(0, 5);
  const visible = cards.filter(job => !["DONE", "CANCELLED"].includes(stateOf(job)) || (showCompleted && completed.includes(job)))
    .sort((a, b) => order.indexOf(stateOf(a)) - order.indexOf(stateOf(b)));
  return <div className="task-queue">
    {error && <p role="alert" className="mt-4 text-sm">{t("Activity updates are unavailable. Previous information is retained.")}</p>}
    {loading && <p role="status" className="mt-4 text-sm muted">{t("Loading activity…")}</p>}
    {!cards.length && !error && !loading && <p className="mt-4 text-sm muted">{t("No activity yet.")}</p>}
    <ol ref={list} className="mt-4 space-y-3" aria-label={t("Activity items")}>
      {visible.map(job => {
        const state = stateOf(job);
        const clarification = state === "PAUSED";
        const resultState = job.result_status || (job.request_status === "PARTIAL" ? "partial" : "pending");
        const status = job.publication_status === "UNCERTAIN" ? "Publication uncertain"
          : job.analysis_state === "scope_rejected" ? "Outside project scope" : clarification ? "Needs clarification" : state === "ERROR" ? "Technical failure"
          : state === "WAITING_AI" ? "Waiting for an AI resource" : state === "QUEUED" ? "In queue"
          : job.kind === "publication" && state === "DONE" ? "Ticket published"
          : job.kind === "discussion" && state === "RUNNING" ? "The assistant is replying…"
          : job.analysis_state && resultStates[job.analysis_state] ? resultStates[job.analysis_state]
          : state === "DONE" && resultState === "partial" ? "Partial result"
          : state === "DONE" ? "Completed" : state === "CANCELLED" ? "Cancelled" : job.kind === "sync" ? "Synchronizing" : job.kind === "publication" ? "Publishing ticket" : "Analysis in progress";
        const waiting = clarification ? waitingDuration(job.clarification_since || job.finished_at, now)
          : ["QUEUED", "WAITING_AI"].includes(state) ? waitingDuration(job.queued_since || (!job.started_at ? job.created_at : null), now) : null;
        const active = job.kind === "analysis" ? job.active_analysis_seconds
          : job.started_at ? Math.max(0, Math.floor((now - Date.parse(job.started_at)) / 1000)) : null;
        const timing = clarification && waiting ? t("Waiting for your answer for {duration}", { duration: waiting })
          : waiting ? t("In queue for {duration}", { duration: waiting })
          : state === "RUNNING" && typeof active === "number" ? t(job.kind === "analysis" ? "Active AI: {minutes}m {seconds}s" : "Elapsed: {minutes}m {seconds}s", { minutes: Math.floor(active / 60), seconds: active % 60 }) : "";
        const action = job.analysis_state === "scope_rejected" ? "Revise analysis" : clarification ? "Answer" : state === "ERROR" ? "See the problem" : job.kind === "sync" ? "Open environment" : "Open analysis";
        return <li key={job.id} data-job={String(job.id)} className="queue-card" data-state={state} data-result-status={resultState}>
          <div className="p-3">
            <span className="badge" data-state={state === "WAITING_AI" ? "QUEUED" : state === "PAUSED" ? "NEEDS_CLARIFICATION" : state === "DONE" && resultState === "partial" ? "PARTIAL" : state}>{t(status)}</span>
            <h3 className="mt-3 line-clamp-2 break-words text-sm font-semibold" title={job.title}>{job.title || t("Analysis")}</h3>
            {state === "ERROR" && <p className="mt-1 text-xs muted">{t("Analysis interrupted")}</p>}
            {state === "RUNNING" && job.stage_number && job.stage_count ? <p className="mt-1 text-xs muted">{t("Step {step} of {total}", { step: job.stage_number, total: job.stage_count })}</p> : null}
            {timing && <p className="mt-1 text-xs muted">{timing}</p>}
            <Link href={job.href || "/analyses"} className="mt-3 inline-block rounded text-sm font-medium text-primary underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-primary">{t(action)}</Link>
          </div>
          {job.can_cancel && job.request_id && <div className="border-t p-2"><AnalysisCancelButton requestId={job.request_id} workflow={job.workflow} title={job.title} /></div>}
        </li>;
      })}
    </ol>
    {!!completed.length && <button type="button" className="mt-4 inline-flex items-center gap-2 rounded text-xs text-primary focus-visible:outline-2 focus-visible:outline-primary" aria-expanded={showCompleted} onClick={() => setShowCompleted(value => !value)}><ChevronDown size={14} aria-hidden="true" />{t(showCompleted ? "Hide recent completed activity" : "Show recent completed activity")}</button>}
    <Link href="/analyses" className="mt-4 block text-xs text-primary underline">{t("Activity history")}</Link>
  </div>;
}
