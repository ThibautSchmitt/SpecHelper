"use client";
import Link from "next/link";
import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  Fragment,
} from "react";
import { ChevronDown, Activity, Bot, CheckCircle2, Clock3, GitBranch, LoaderCircle, PauseCircle, ShieldCheck, Ticket, UserRound, UsersRound, XCircle } from "lucide-react";
import { AssistantLogo } from "@/components/assistant-logo";
import { AnalysisCancelButton } from "@/components/analysis-cancel-button";
import { AnalysisRetryButton } from "@/components/analysis-retry-button";
import { api, resultStates } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { assistantName } from "@/lib/assistant-providers";
import {
  roleLabels,
  warningMessage,
  type AnalysisWarning,
} from "@/lib/orchestration";

export type QueueJob = {
  id: number | string;
  kind: string;
  workflow?: "request" | "question";
  status: string;
  queue_state?: string;
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
    const key = job.kind === "analysis" && job.request_id ? `analysis:${job.request_id}` : `${job.kind}:${job.id}`;
    const previous = latest.get(key);
    if (!previous || Date.parse(job.created_at) > Date.parse(previous.created_at) || (job.created_at === previous.created_at && Number(job.id) > Number(previous.id))) latest.set(key, job);
  }
  return Array.from(latest.values()).filter(job => !(job.kind === "sync" && stateOf(job) === "DONE"));
}

export function useQueueAttention() {
  const { jobs, error } = useContext(QueueContext);
  const cards = queueCards(jobs);
  return { count: cards.filter(job => ["PAUSED", "ERROR"].includes(stateOf(job)) || job.result_status === "partial").length,
    clarifications: cards.filter(job => stateOf(job) === "PAUSED").length, error: !!error };
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
  const groups = [
    { state: "RUNNING", label: "In progress", icon: LoaderCircle },
    { state: "QUEUED", label: "Waiting", icon: Clock3 },
    { state: "WAITING_AI", label: "Waiting for AI", icon: Clock3 },
    { state: "PAUSED", label: "Needs clarification", icon: PauseCircle },
    { state: "ERROR", label: "Failed", icon: XCircle },
    { state: "CANCELLED", label: "Cancelled", icon: XCircle },
    { state: "DONE", label: "Completed", icon: CheckCircle2 },
  ];
  // Retained jobs are history, not additional live cards for the same request.
  // The newest analysis owns the card even if an older attempt had a higher state.
  const cards = queueCards(jobs);
  const recent = cards
    .filter((j) => ["DONE", "ERROR", "CANCELLED"].includes(stateOf(j)))
    .sort((a, b) => Date.parse(b.finished_at || b.created_at) - Date.parse(a.finished_at || a.created_at))
    .slice(0, 5);
  const visible = groups.flatMap((group) =>
    cards.filter(
      (job) =>
        stateOf(job) === group.state &&
        (!["DONE", "CANCELLED"].includes(group.state) || recent.includes(job)),
    ),
  );

  return (
    <div className="task-queue">
      <h2 className="flex items-center gap-2">
        <Activity size={18} aria-hidden="true" />
        {t("Task queue")}
        <span className="queue-total">{visible.length}</span>
      </h2>
      <p className="mt-2 text-xs muted">
        {t("Shared activity across all pages and browsers.")}
      </p>
      {error && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {t(error)}
        </p>
      )}
      {loading && (
        <p className="mt-6 text-sm muted" role="status">
          {t("Loading tasks…")}
        </p>
      )}
      {!visible.length && !error && !loading && (
        <p className="mt-6 text-sm muted">{t("No tasks yet.")}</p>
      )}
      <ol ref={list} className="mt-5 space-y-2" aria-label={t("Tasks")}>
        {visible.map((job, jobIndex) => {
          const state = stateOf(job);
          const clarification = state === "PAUSED";
          const group = groups.find((group) => group.state === state)!;
          const firstInGroup =
            jobIndex === 0 || stateOf(visible[jobIndex - 1]) !== state;
          const assignment = job.assignments?.at(-1);
          const previous = job.assignment_state === "previous" || (job.assignment_state !== "current" && state !== "RUNNING");
          const assistant = assignment?.connection_name || (assignment?.agent ? assistantName(assignment.agent) : t("Recorded AI"));
          const role = assignment?.public_role || job.public_role;
          const roleName = role ? t(roleLabels[role] || role) : "";
          const RoleIcon = role === "verifier" ? ShieldCheck : role === "counter_analyst" ? UsersRound : UserRound;
          const warning = job.warnings?.map((value) => t(warningMessage(value))).join(" · ");
          const description = t(job.error || job.pause_reason || job.waiting_reason || (clarification ? "A business answer is needed." : job.stage || job.operation || job.kind));
          const resultState = job.result_status || (job.request_status === "PARTIAL" ? "partial" : job.request_status === "READY" ? "complete" : ["ERROR", "CANCELLED"].includes(job.request_status) ? "unusable" : "pending");
          const resultLabel = resultState === "partial" ? "Partial result" : resultState === "complete" ? "Complete result" : resultState === "unusable" ? "No usable result" : "";
          const limits = job.result_limits?.map(reason => t(reason)).join(" · ") || (resultState === "partial" ? t("Required independent checks are incomplete. Publication is blocked.") : "");
          const identifier = `#${String(job.id).replace(/^publication:/, "").slice(0, typeof job.id === "number" ? undefined : 8)}`;
          const elapsed = job.kind === "analysis" ? job.active_analysis_seconds ?? null : job.started_at
            ? Math.max(
                0,
                Math.floor(
                  ((job.finished_at ? Date.parse(job.finished_at) : now) -
                    Date.parse(job.started_at)) /
                    1000,
                ),
              )
            : null;
          const waiting = clarification ? waitingDuration(job.clarification_since || job.finished_at, now)
            : ["QUEUED", "WAITING_AI"].includes(state) ? waitingDuration(job.queued_since || (!job.started_at ? job.created_at : null), now) : null;
          const timing = clarification ? (waiting ? t("Waiting for your answer for {duration}", { duration: waiting }) : t("Your answer is needed"))
            : ["QUEUED", "WAITING_AI"].includes(state) ? (waiting ? t("In queue for {duration}", { duration: waiting }) : t("Waiting for a resource")) : "";
          return (
            <Fragment key={job.id}>
              {firstInGroup && (
                <li className="queue-group-heading" role="presentation">
                  {state === "DONE" ? <h3 data-state={state}><button type="button" className="flex w-full items-center gap-2 text-left" aria-expanded={showCompleted} onClick={() => setShowCompleted(value => !value)}><group.icon size={14} aria-hidden="true" />{t(group.label)} ({visible.filter((item) => stateOf(item) === state).length})<ChevronDown className={`ml-auto transition-transform ${showCompleted ? "rotate-180" : ""}`} size={14} aria-hidden="true" /></button></h3> : <h3 data-state={state}><group.icon size={14} aria-hidden="true" />{t(group.label)} ({visible.filter((item) => stateOf(item) === state).length})</h3>}
                </li>
              )}
              {(state !== "DONE" || showCompleted) && <li
                data-job={String(job.id)}
                className="queue-card"
                data-state={state}
                data-result-status={resultState}
              >
                <Link href={job.href || "/"} className="queue-card-content">
                  <div className="queue-card-title">
                    <strong title={job.title || t("Request")}>{job.title || t("Request")}</strong>
                    <span className="queue-identifier" title={t("Task {id}", { id: String(job.id) })}>{identifier}</span>
                  </div>
                  <div className="queue-card-status">
                    <group.icon className={state === "RUNNING" ? "queue-running-icon" : ""} size={17} aria-hidden="true" />
                    <span className="badge" data-state={state === "DONE" && resultState === "partial" ? "PARTIAL" : state}>
                      <group.icon size={11} aria-hidden="true" />
                      {t(job.publication_status === "UNCERTAIN" ? "Publication uncertain" : job.kind === "publication" && state === "DONE" ? "Ticket published" : job.analysis_state && job.analysis_state !== "processing" && resultStates[job.analysis_state] ? resultStates[job.analysis_state] : state === "PAUSED" ? "Needs clarification" : state === "ERROR" ? "Technical failure" : state === "DONE" && job.kind === "analysis" ? resultLabel || "Processing completed" : group.label)}
                    </span>
                    <span className="queue-context" title={[job.environment_name, job.stage].filter(Boolean).join(" · ")}>
                      {job.status === "QUEUED" && job.queue_position != null
                        ? t("Queue position: {position}", { position: job.queue_position })
                        : clarification ? t("Your answer is needed") : job.environment_name || t(job.operation || job.kind)}
                    </span>
                  </div>
                  <div className="queue-assistants">
                    {["sync", "publication"].includes(job.kind) ? (
                      <span className="queue-executor" title={t("No AI execution")}>
                        {job.kind === "sync" ? <GitBranch size={17} aria-hidden="true" /> : <Ticket size={17} aria-hidden="true" />}
                        {job.executor_name || t(job.kind === "sync" ? "Git synchronization" : "Ticket connector")} · {t("No AI execution")}
                      </span>
                    ) : assignment ? (
                      <>
                        <span className="queue-assignment" data-assignment={previous ? "previous" : "current"} title={[t(previous ? "Previous AI" : "Current AI"), assistant, assignment.model && assignment.model !== "runtime-default" ? assignment.model : t("Provider default model"), roleName].filter(Boolean).join(" · ")}>
                          <AssistantLogo agent={assignment.agent} />
                          {previous && <span className={state === "RUNNING" ? "" : "sr-only"}>{t("Previous AI")}: </span>}
                          <span className="queue-assistant-name">{assistant}</span>
                        </span>
                        {roleName && <span className="queue-role" title={roleName}><RoleIcon size={13} aria-hidden="true" /><span>{roleName}</span></span>}
                        <span className="queue-model" title={[assistantName(assignment.agent), assignment.model && assignment.model !== "runtime-default" ? assignment.model : t("Provider default model")].join(" · ")}>
                          {assignment.model && assignment.model !== "runtime-default" ? assignment.model : t("Provider default model")}
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="queue-assignment"><Bot size={16} aria-hidden="true" /><span className="queue-assistant-name">{t("AI not assigned")}</span></span>
                        {roleName && <span className="queue-role" title={roleName}><RoleIcon size={13} aria-hidden="true" /><span>{roleName}</span></span>}
                      </>
                    )}
                  </div>
                  <p className="queue-description" data-error={!!job.error} title={[description, warning].filter(Boolean).join(" · ")}>{warning && !job.error ? `${warning} · ${description}` : description}</p>
                  {(job.stage_number || elapsed !== null || timing) && <p className="mt-2 flex flex-wrap justify-between gap-2 text-xs muted">
                    {job.stage_number && job.stage_count === 3 ? <span>{t("Step {step} of {total}", { step: job.stage_number, total: job.stage_count })}</span> : <span />}
                    {timing && <span>{timing}</span>}
                    {elapsed !== null && <span>{t(job.kind === "analysis" ? "Active AI: {minutes}m {seconds}s" : "Elapsed: {minutes}m {seconds}s", { minutes: Math.floor(elapsed / 60), seconds: elapsed % 60 })}</span>}
                  </p>}
                  {job.kind === "analysis" && resultLabel && <div className="mt-2 text-xs" data-result-status={resultState}>
                    {!job.analysis_state && <p className={resultState === "partial" ? "font-medium text-amber-700 dark:text-amber-300" : "muted"}>{t(resultLabel)}</p>}
                    {limits && <p className="mt-1 line-clamp-2 muted" title={limits}>{limits}</p>}
                  </div>}
                </Link>
                {job.can_cancel && job.request_id && <div className="border-t px-1"><AnalysisCancelButton requestId={job.request_id} workflow={job.workflow} title={job.title} /></div>}
                {job.can_retry && job.request_id && ["ERROR", "CANCELLED"].includes(state) && <div className="border-t p-2"><AnalysisRetryButton requestId={job.request_id} workflow={job.workflow} title={job.title} /></div>}
              </li>}
            </Fragment>
          );
        })}
      </ol>
      <p className="mt-5 text-xs muted">
        {t(
          "Only recent completed tasks are shown here. Open Analyses or Tickets for full history.",
        )}
      </p>
      <Link href="/analyses" className="mt-2 inline-block text-xs text-primary underline">{t("Analysis history")}</Link>
    </div>
  );
}
