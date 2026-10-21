"use client";
import { useI18n } from "@/lib/i18n";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import {
  ArrowLeft,
  Check,
  Copy,
  Download,
  MessageCircle,
  Paperclip,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  send,
  statuses,
  type RequestDetail,
  type ResultVersion,
} from "@/lib/api";

const labels: Record<string, string> = {
  context: "Context",
  requirements: "Requirements",
  technical_impact: "Technical impacts",
  business_need: "Business need",
  current_behavior: "Current behavior",
  expected_behavior: "Expected behavior",
  decisions: "Questions and decisions",
  acceptance_criteria: "Acceptance criteria",
  proposed_solution: "Proposed solution",
  technical_analysis: "Technical analysis",
  components: "Affected components",
  database_impact: "Data impact",
  risks: "Risks and considerations",
  tests: "Expected tests",
};
const active = [
  "QUEUED",
  "UNDERSTANDING",
  "ANALYZING",
  "GENERATING_TICKET",
  "REVIEWING",
  "GENERATING_RESULT",
  "CONTINUING_CONVERSATION",
];
const currentLabels: Record<string, string> = {
  context: "Context",
  need: "Need",
  expected_behavior: "Expected behavior",
  proposed_solution: "Proposed solution",
  technical_impact: "Technical impacts",
  risks: "Risks and considerations",
  acceptance_criteria: "Acceptance criteria",
};
const conciseLabels: Record<string, string> = {
  context: "Context",
  requirements: "Requirements",
  proposed_solution: "Proposed solution",
  technical_impact: "Technical impacts",
  risks: "Risks and considerations",
  acceptance_criteria: "Acceptance criteria",
};

export default function RequestPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { t, dateLocale } = useI18n();
  const { id } = use(params);
  const [value, setValue] = useState<RequestDetail | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<ResultVersion | null>(
    null,
  );
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null);
  const [showDiscussion, setShowDiscussion] = useState(false);
  const [message, setMessage] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [goalCopied, setGoalCopied] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () =>
      api<RequestDetail>(`/requests/${id}`)
        .then((v) => {
          if (alive) {
            setValue(v);
            setError("");
          }
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    load();
    const timer = setInterval(load, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [id]);
  useEffect(() => {
    if (selectedNumber === null) {
      setSelectedVersion(null);
      return;
    }
    let alive = true;
    api<ResultVersion>(`/requests/${id}/versions/${selectedNumber}`)
      .then((v) => {
        if (alive) setSelectedVersion(v);
      })
      .catch((e) => {
        if (alive) {
          setError(e.message);
          setSelectedNumber(null);
        }
      });
    return () => {
      alive = false;
    };
  }, [id, selectedNumber]);
  const loadingVersion =
    selectedNumber !== null && selectedVersion?.number !== selectedNumber;
  const result =
    selectedNumber === null ? value?.latest_version : selectedVersion;
  const ticket = loadingVersion ? null : result?.ticket || value?.ticket;
  async function continueDiscussion(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setValue(
        await send<RequestDetail>(`/requests/${id}/continue`, {
          message,
          expected_version: value!.latest_version!.number,
        }),
      );
      setMessage("");
      setShowDiscussion(false);
      setSelectedNumber(null);
      setSelectedVersion(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setValue(
        await send<RequestDetail>(`/requests/${id}/answers`, { answers }),
      );
      setAnswers({});
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function copyGoal() {
    try {
      await navigator.clipboard.writeText(result!.goal_markdown);
      setGoalCopied(true);
      setTimeout(() => setGoalCopied(false), 2500);
    } catch {
      setError(
        t("Copying is unavailable in this browser. Download goal.md instead."),
      );
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(result?.markdown || value!.markdown!);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError(
        t(
          "Copying is unavailable in this browser. Download the Markdown instead.",
        ),
      );
    }
  }
  if (!value)
    return (
      <div role={error ? "alert" : "status"}>
        {error ? t(error) : t("Loading request…")}
      </div>
    );
  return (
    <div className="space-y-6">
      <Link href="/" className="inline-flex items-center gap-2 text-sm muted">
        <ArrowLeft size={16} /> {t("All requests")}
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-primary">
            {value.environment_name} {t("· Request")} {value.id.slice(0, 8)}
          </p>
          <h1>{ticket?.title || t("Your request")}</h1>
        </div>
        <span role="status" className="badge" data-state={value.status}>
          {t(statuses[value.status])}
        </span>
      </div>
      {(error || value.error) && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"
        >
          {t(error || value.error)}
        </div>
      )}
      <Card>
        <h2>{t("Your original need")}</h2>
        <p className="mt-3 whitespace-pre-wrap leading-7">{value.need}</p>
        {value.understanding && (
          <div className="mt-5 rounded-lg bg-muted p-4">
            <h3 className="text-sm">{t("What SpecHelper understood")}</h3>
            <p className="mt-2 text-sm leading-6">{value.understanding}</p>
          </div>
        )}
        {value.attachments.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-3">
            {value.attachments.map((a) => (
              <a
                key={a.id}
                className="flex items-center gap-1 rounded-md border px-3 py-2 text-sm text-primary"
                href={`/api/requests/${id}/attachments/${a.id}`}
              >
                <Paperclip size={14} />
                {a.name}
              </a>
            ))}
          </div>
        )}
      </Card>
      {active.includes(value.status) && (
        <Card aria-live="polite">
          <h2>
            {["QUEUED", "CONTINUING_CONVERSATION"].includes(value.status)
              ? t("Your request is queued")
              : t("SpecHelper is preparing your ticket")}
          </h2>
          <p className="mt-2 text-sm muted">
            {["QUEUED", "CONTINUING_CONVERSATION"].includes(value.status)
              ? t(
                  "It will be processed when an assistant is available. Queue time does not reduce analysis time.",
                )
              : t(
                  "An analysis is limited to five minutes once started. You can leave this page and return later.",
                )}
          </p>
          <ol className="mt-5 space-y-3">
            {value.progress.map((p, i) => (
              <li key={i} className="flex items-center gap-3 text-sm">
                <Check className="text-primary" size={16} />
                {t(p.label)}
              </li>
            ))}
            <li className="text-sm font-medium text-primary">
              {t(statuses[value.status])}…
            </li>
          </ol>
        </Card>
      )}
      {["QUEUED", "CONTINUING_CONVERSATION"].includes(value.status) && (
        <p className="text-sm muted">
          {t("You can")}{" "}
          <Link href="/admin" className="text-primary underline">
            {t("check connections in Administration")}
          </Link>{" "}
          {t("or return later.")}
        </p>
      )}
      {value.confrontation && (
        <p className="text-sm muted">
          {["READY", "PARTIAL"].includes(value.status)
            ? t("This result combines two independent analyses.")
            : t("A comparison of two independent analyses was requested.")}
        </p>
      )}
      {value.status === "DRAFT" && (
        <Card>
          <p className="mb-4">
            {t("This request is saved and ready to start.")}
          </p>
          <Button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                setValue(await send<RequestDetail>(`/requests/${id}/analyze`));
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("Analyze this request")}
          </Button>
        </Card>
      )}
      {value.messages?.length > 0 && (
        <details className="rounded-xl border bg-card p-5">
          <summary className="cursor-pointer font-medium">
            {t("Discussion history")}
          </summary>
          <div className="mt-4 space-y-5">
            {value.messages
              .filter((m) => m.kind !== "need")
              .map((m) => (
                <div key={m.id}>
                  <p className="text-xs font-semibold muted">
                    {m.role === "user" ? t("You") : "SpecHelper"}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-sm">
                    {m.kind === "result" || m.kind === "error" ? t(m.content) : m.content}
                  </p>
                </div>
              ))}
          </div>
        </details>
      )}
      {value.status === "NEEDS_CLARIFICATION" && (
        <Card className="border-primary/40">
          <h2 className="flex items-center gap-2">
            <MessageCircle size={20} className="text-primary" />{" "}
            {t("A few details before continuing")}
          </h2>
          <p className="mt-2 text-sm muted">
            {t("Your answers will help prepare a suitable proposal.")}
          </p>
          <form onSubmit={submit}>
            {value.questions.map((q) => (
              <div key={q.id} className="field">
                <label htmlFor={q.id}>{q.question}</label>
                <Textarea
                  id={q.id}
                  required
                  maxLength={10000}
                  value={answers[q.id] || ""}
                  onChange={(e) =>
                    setAnswers({ ...answers, [q.id]: e.target.value })
                  }
                />
              </div>
            ))}
            <Button className="mt-5" disabled={busy}>
              {busy ? t("Sending…") : t("Answer and continue")}
            </Button>
          </form>
        </Card>
      )}
      {loadingVersion && (
        <p role="status">{t("Loading the selected version…")}</p>
      )}
      {ticket && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <h2>{t("Proposed ticket")}</h2>
              {!!value.versions?.length && (
                <div>
                  <label className="sr-only" htmlFor="result-version">
                    {t("Result version")}
                  </label>
                  <select
                    id="result-version"
                    value={selectedNumber ?? "latest"}
                    onChange={(e) => {
                      setSelectedVersion(null);
                      setSelectedNumber(
                        e.target.value === "latest"
                          ? null
                          : Number(e.target.value),
                      );
                    }}
                  >
                    <option value="latest">
                      {t("Current version · v")}
                      {value.latest_version?.number}
                    </option>
                    {value.versions
                      .filter((v) => v.number !== value.latest_version?.number)
                      .map((v) => (
                        <option key={v.number} value={v.number}>
                          {t("Version")} {v.number} ·{" "}
                          {new Date(v.created_at).toLocaleString(dateLocale)}
                        </option>
                      ))}
                  </select>
                </div>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={copy}>
                <Copy size={16} />
                {copied ? t("Copied!") : t("Copy for Jira")}
              </Button>
              <Button asChild>
                <a
                  href={
                    result?.artifacts["ticket.md"] ||
                    `/api/requests/${id}/markdown`
                  }
                >
                  <Download size={16} />
                  Markdown
                </a>
              </Button>
              {result?.goal_markdown && (
                <Button variant="outline" onClick={copyGoal}>
                  <Copy size={16} />
                  {goalCopied ? t("Goal copied!") : t("Copy goal.md")}
                </Button>
              )}
              {result?.artifacts["goal.md"] && (
                <Button variant="outline" asChild>
                  <a href={result.artifacts["goal.md"]}>
                    <Download size={16} />
                    goal.md
                  </a>
                </Button>
              )}
            </div>
          </div>
          <Card className="space-y-7">
            {Object.entries(
              result?.format_version === "1.2"
                ? currentLabels
                : result?.format_version === "1.1"
                  ? conciseLabels
                  : labels,
            )
              .filter(([key]) => ticket[key] !== undefined)
              .map(([key, label]) => (
                <section key={key}>
                  <h3 className="mb-2 text-primary">{t(label)}</h3>
                  {Array.isArray(ticket[key]) ? (
                    <ul className="list-disc space-y-1 pl-5 leading-7">
                      {(ticket[key] as string[]).map((item, i) => (
                        <li key={i} className="break-words">
                          {item}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="ticket-section">{ticket[key]}</p>
                  )}
                </section>
              ))}
          </Card>
        </>
      )}
      {value.latest_version &&
        ["READY", "PARTIAL", "ERROR"].includes(value.status) && (
          <Card>
            <h2>{t("Refine this proposal")}</h2>
            {selectedNumber !== null && (
              <p className="mt-2 text-sm muted">
                {t("The discussion continues from the latest version (v")}
                {value.latest_version.number}).
              </p>
            )}
            <p className="mt-2 text-sm muted">
              {t(
                "Clarify a point or add a constraint. A new version will be created; previous versions will remain available.",
              )}
            </p>
            {!showDiscussion ? (
              <Button className="mt-4" onClick={() => setShowDiscussion(true)}>
                <MessageCircle size={16} />
                {t("Continue the discussion")}
              </Button>
            ) : (
              <form onSubmit={continueDiscussion}>
                <div className="field">
                  <label htmlFor="followup">{t("Your message")}</label>
                  <Textarea
                    id="followup"
                    required
                    minLength={1}
                    maxLength={30000}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    autoFocus
                  />
                </div>
                <div className="mt-4 flex gap-2">
                  <Button disabled={busy || !message.trim()}>
                    {busy ? t("Sending…") : t("Send and update proposal")}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setShowDiscussion(false)}
                  >
                    {t("Cancel")}
                  </Button>
                </div>
              </form>
            )}
          </Card>
        )}
      {!!value.baseline.length && (
        <details className="rounded-xl border bg-card p-5">
          <summary className="cursor-pointer text-sm font-medium">
            {t("Analysis reference")}
          </summary>
          <p className="my-3 text-xs muted">
            {t(
              "These references remain fixed at launch, even if the environment changes.",
            )}
          </p>
          {value.baseline.map((r) => (
            <div key={r.repository} className="mb-3 break-all text-xs">
              <p className="font-semibold">
                {r.repository} · {r.branch}
              </p>
              <code>{r.sha}</code>
            </div>
          ))}
          <p className="text-xs muted">
            {t("Database connection:")} {value.database.name || t("None")}
          </p>
        </details>
      )}
    </div>
  );
}
