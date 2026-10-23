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
import { Activity, Bot, CheckCircle2, Clock3, GitBranch, LoaderCircle, PauseCircle, ShieldCheck, Ticket, UserRound, UsersRound, XCircle } from "lucide-react";
import { AssistantLogo } from "@/components/assistant-logo";
import { api, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
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
    return () => {
      alive = false;
      clearInterval(timer);
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
  const stateOf = (job: QueueJob) =>
    job.queue_state ||
    (job.request_status === "NEEDS_CLARIFICATION" && job.status === "DONE"
      ? "PAUSED"
      : job.status);
  const groups = [
    { state: "RUNNING", label: "In progress", icon: LoaderCircle },
    { state: "QUEUED", label: "Waiting", icon: Clock3 },
    { state: "PAUSED", label: "Needs clarification", icon: PauseCircle },
    { state: "DONE", label: "Completed", icon: CheckCircle2 },
    { state: "ERROR", label: "Failed", icon: XCircle },
  ];
  const recent = jobs
    .filter((j) => ["DONE", "ERROR"].includes(stateOf(j)))
    .slice(0, 8);
  const visible = groups.flatMap((group) =>
    jobs.filter(
      (job) =>
        stateOf(job) === group.state &&
        (!["DONE", "ERROR"].includes(group.state) || recent.includes(job)),
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
          const assistant = assignment?.connection_name || (assignment?.agent === "claude" ? "Claude" : assignment?.agent === "codex" ? "ChatGPT / Codex" : t("Recorded AI"));
          const role = assignment?.public_role || job.public_role;
          const roleName = role ? t(roleLabels[role] || role) : "";
          const RoleIcon = role === "verifier" ? ShieldCheck : role === "counter_analyst" ? UsersRound : UserRound;
          const warning = job.warnings?.map((value) => t(warningMessage(value))).join(" · ");
          const description = t(job.error || job.pause_reason || job.waiting_reason || (clarification ? "A business answer is needed." : job.stage || job.operation || job.kind));
          const identifier = `#${String(job.id).replace(/^publication:/, "").slice(0, typeof job.id === "number" ? undefined : 8)}`;
          const elapsed = job.started_at
            ? Math.max(
                0,
                Math.floor(
                  ((job.finished_at ? Date.parse(job.finished_at) : now) -
                    Date.parse(job.started_at)) /
                    1000,
                ),
              )
            : null;
          return (
            <Fragment key={job.id}>
              {firstInGroup && (
                <li className="queue-group-heading" role="presentation">
                  <h3 data-state={state}><group.icon size={14} aria-hidden="true" />{t(group.label)} ({visible.filter((item) => stateOf(item) === state).length})</h3>
                </li>
              )}
              <li
                data-job={String(job.id)}
                className="queue-card"
                data-state={state}
              >
                <Link href={job.href || "/"} className="queue-card-content">
                  <div className="queue-card-title">
                    <strong title={job.title || t("Request")}>{job.title || t("Request")}</strong>
                    <span className="queue-identifier" title={t("Task {id}", { id: String(job.id) })}>{identifier}</span>
                  </div>
                  <div className="queue-card-status">
                    <group.icon className={state === "RUNNING" ? "queue-running-icon" : ""} size={17} aria-hidden="true" />
                    <span className="badge" data-state={state}>
                      <group.icon size={11} aria-hidden="true" />
                      {t(job.publication_status === "UNCERTAIN" ? statuses.UNCERTAIN : state === "PAUSED" ? "Paused" : state === "ERROR" ? "Error" : group.label)}
                    </span>
                    <span className="queue-context" title={[job.environment_name, job.stage, elapsed !== null ? t("Elapsed: {minutes}m {seconds}s", { minutes: Math.floor(elapsed / 60), seconds: elapsed % 60 }) : ""].filter(Boolean).join(" · ")}>
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
                      </>
                    ) : (
                      <>
                        <span className="queue-assignment"><Bot size={16} aria-hidden="true" /><span className="queue-assistant-name">{t("AI not assigned")}</span></span>
                        {roleName && <span className="queue-role" title={roleName}><RoleIcon size={13} aria-hidden="true" /><span>{roleName}</span></span>}
                      </>
                    )}
                  </div>
                  <p className="queue-description" data-error={!!job.error} title={[description, warning].filter(Boolean).join(" · ")}>{warning && !job.error ? `${warning} · ${description}` : description}</p>
                </Link>
              </li>
            </Fragment>
          );
        })}
      </ol>
      <p className="mt-5 text-xs muted">
        {t(
          "Recent completed tasks are shown here. Open Requests, Questions or Tickets for full history.",
        )}
      </p>
    </div>
  );
}
