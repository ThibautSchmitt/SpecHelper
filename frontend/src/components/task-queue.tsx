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
import { Clock3 } from "lucide-react";
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
    { state: "RUNNING", label: "In progress" },
    { state: "QUEUED", label: "Waiting" },
    { state: "PAUSED", label: "Needs clarification" },
    { state: "DONE", label: "Completed" },
    { state: "ERROR", label: "Failed" },
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
        <Clock3 size={18} />
        {t("Task queue")}
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
      <ol ref={list} className="mt-5 space-y-3" aria-label={t("Tasks")}>
        {visible.map((job, jobIndex) => {
          const state = stateOf(job);
          const clarification = state === "PAUSED";
          const group = groups.find((group) => group.state === state)!;
          const firstInGroup =
            jobIndex === 0 || stateOf(visible[jobIndex - 1]) !== state;
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
                  <h3>{t(group.label)}</h3>
                </li>
              )}
              <li
                data-job={String(job.id)}
                className="queue-card"
                data-state={state}
              >
                <Link href={job.href || "/"} className="block p-3">
                  <div className="flex items-start justify-between gap-2">
                    <strong className="break-words text-sm">
                      {job.title || t("Request")}
                    </strong>
                    {job.environment_name && (
                      <span
                        className="queue-environment"
                        title={job.environment_name}
                      >
                        {job.environment_name}
                      </span>
                    )}
                  </div>
                  {job.workflow === "question" && (
                    <p className="mt-2 text-xs font-medium text-primary">
                      {t("Question")}
                    </p>
                  )}
                  <p className="mt-2">
                    <span className="badge" data-state={state}>
                      {t(
                        clarification
                          ? "Needs clarification"
                          : statuses[
                              job.publication_status === "UNCERTAIN"
                                ? "UNCERTAIN"
                                : state
                            ] || state,
                      )}
                    </span>
                  </p>
                  <p className="mt-1 text-xs muted">
                    {t(job.operation || job.kind)}
                  </p>
                  <p className="queue-identifier mt-1 text-xs muted">
                    {t("Task {id}", { id: String(job.id) })}
                  </p>
                  {["sync", "publication"].includes(job.kind) && (
                    <p className="mt-1 text-xs muted">
                      {job.executor_name ||
                        t(
                          job.kind === "sync"
                            ? "Git synchronization"
                            : "Ticket connector",
                        )}{" "}
                      · {t("No AI execution")}
                    </p>
                  )}
                  {!["sync", "publication"].includes(job.kind) && (
                    <div className="mt-1 space-y-1 text-xs muted">
                      {job.assignments?.length ? (
                        job.assignments.map((assignment, index) => (
                          <p
                            key={`${assignment.connection_id}-${index}`}
                            className="break-words"
                          >
                            {job.assignment_state === "previous" && (
                              <>{t("Previous AI")}: </>
                            )}
                            {assignment.connection_name ||
                              (assignment.agent === "claude"
                                ? "Claude"
                                : assignment.agent === "codex"
                                  ? "ChatGPT / Codex"
                                  : t("Recorded AI"))}{" "}
                            ·{" "}
                            {!assignment.model ||
                            assignment.model === "runtime-default"
                              ? t("Provider default model")
                              : assignment.model}
                            {(assignment.public_role || job.public_role) &&
                              ` · ${t(roleLabels[assignment.public_role || job.public_role || ""] || assignment.public_role || job.public_role || "")}`}
                          </p>
                        ))
                      ) : (
                        <p>
                          {t("AI not assigned")}
                          {job.public_role &&
                            ` · ${t(roleLabels[job.public_role] || job.public_role)}`}
                        </p>
                      )}
                    </div>
                  )}
                  {(job.stage || job.pause_reason || job.waiting_reason) && (
                    <p className="queue-stage mt-2 text-xs muted">
                      {t(
                        job.pause_reason ||
                          job.waiting_reason ||
                          job.stage ||
                          "",
                      )}
                    </p>
                  )}
                  {job.status === "QUEUED" && job.queue_position != null && (
                    <p className="mt-1 text-xs muted">
                      {t("Queue position: {position}", {
                        position: job.queue_position,
                      })}
                    </p>
                  )}
                  {elapsed !== null && (
                    <p className="mt-1 text-xs muted">
                      {t("Elapsed: {minutes}m {seconds}s", {
                        minutes: Math.floor(elapsed / 60),
                        seconds: elapsed % 60,
                      })}
                    </p>
                  )}
                  {clarification && !job.pause_reason && (
                    <p className="mt-1 text-xs muted">
                      {t("A business answer is needed.")}
                    </p>
                  )}
                  {job.error && (
                    <p className="mt-2 break-words text-xs text-red-800">
                      {t(job.error)}
                    </p>
                  )}
                  {!!job.warnings?.length && (
                    <ul
                      className="mt-2 space-y-1 text-xs text-amber-800"
                      aria-label={t("Analysis warnings")}
                    >
                      {job.warnings.map((warning, index) => (
                        <li key={index}>{t(warningMessage(warning))}</li>
                      ))}
                    </ul>
                  )}
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
