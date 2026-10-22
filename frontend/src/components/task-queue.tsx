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
import { Clock3 } from "lucide-react";
import { api, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export type QueueJob = {
  id: number | string;
  kind: string;
  status: string;
  publication_status?: string;
  title: string;
  environment_name: string;
  operation: string;
  agent: string;
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
}>({ jobs: [], error: "", now: 0 });
export function TaskQueueProvider({ children }: { children: React.ReactNode }) {
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    let alive = true;
    const update = () =>
      api<QueueJob[]>("/queue")
        .then((value) => {
          if (alive) {
            setJobs(value);
            setError("");
            setNow(Date.now());
          }
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    update();
    const timer = setInterval(update, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  return (
    <QueueContext.Provider value={{ jobs, error, now }}>
      {children}
    </QueueContext.Provider>
  );
}

export function TaskQueue() {
  const { t } = useI18n();
  const { jobs, error, now } = useContext(QueueContext);
  const list = useRef<HTMLOListElement>(null);
  const positions = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const next = new Map<string, number>();
    for (const element of Array.from(
      list.current?.children || [],
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
  const visible = jobs
    .filter((j) => !["DONE", "ERROR"].includes(j.status))
    .concat(
      jobs.filter((j) => ["DONE", "ERROR"].includes(j.status)).slice(0, 8),
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
      {!visible.length && !error && (
        <p className="mt-6 text-sm muted">{t("No tasks yet.")}</p>
      )}
      <ol ref={list} className="mt-5 space-y-3" aria-label={t("Tasks")}>
        {visible.map((job) => {
          const clarification =
            job.request_status === "NEEDS_CLARIFICATION" &&
            job.status === "DONE";
          const state =
            job.publication_status === "UNCERTAIN"
              ? "UNCERTAIN"
              : clarification
                ? "NEEDS_CLARIFICATION"
                : job.status;
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
            <li
              key={job.id}
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
                    <span className="queue-environment">
                      {job.environment_name}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-xs font-semibold">
                  {t(statuses[state] || state)}
                </p>
                <p className="mt-1 text-xs muted">
                  {t(job.operation || job.kind)}
                  {job.agent && ` · ${job.agent}`}
                </p>
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
                {clarification && (
                  <p className="mt-1 text-xs muted">
                    {t("A business answer is needed.")}
                  </p>
                )}
                {job.error && (
                  <p className="mt-2 break-words text-xs text-red-800">
                    {t(job.error)}
                  </p>
                )}
              </Link>
            </li>
          );
        })}
      </ol>
      <p className="mt-5 text-xs muted">
        {t(
          "Recent completed tasks are shown here. Open Requests or Tickets for full history.",
        )}
      </p>
    </div>
  );
}
