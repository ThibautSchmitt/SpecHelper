"use client";
import { BusinessClarification, BusinessDecisions, BusinessOverview } from "@/components/business-clarification";
import { QuestionResult } from "@/components/question-result";
import { PublishTicket } from "@/components/publish-ticket";
import { AnalysisContext } from "@/components/analysis-context";
import { AnalysisEvidence } from "@/components/analysis-evidence";
import { AnalysisCancelButton } from "@/components/analysis-cancel-button";
import { AnalysisRetryButton } from "@/components/analysis-retry-button";
import { ScopeAssessmentPanel } from "@/components/scope-assessment";
import { useI18n } from "@/lib/i18n";
import { roleLabels, warningMessage } from "@/lib/orchestration";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use, useEffect, useState } from "react";
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
  scopeNeedsContext,
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

export function WorkItemDetail(props: {
  params: Promise<{ id: string }>;
  workflow?: "request" | "question";
}) {
  return (
    <Suspense>
      <RequestContent {...props} />
    </Suspense>
  );
}

function RequestContent({
  params,
  workflow = "request",
}: {
  params: Promise<{ id: string }>;
  workflow?: "request" | "question";
}) {
  const isQuestion = workflow === "question";
  const base = isQuestion ? "/questions" : "/requests";
  const { t, dateLocale } = useI18n();
  const { id } = use(params);
  const search = useSearchParams();
  const router = useRouter();
  const [value, setValue] = useState<RequestDetail | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<ResultVersion | null>(
    null,
  );
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null);
  const [showDiscussion, setShowDiscussion] = useState(false);
  useEffect(() => {
    if (isQuestion && window.location.hash === "#discussion")
      setShowDiscussion(true);
  }, [isQuestion]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [goalCopied, setGoalCopied] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (value?.scope_pending_message) {
      setMessage((current) => current || value.scope_pending_message || "");
      setShowDiscussion(true);
    }
  }, [value?.id, value?.scope_pending_message]);
  useEffect(() => {
    const version = Number(search.get("version"));
    setSelectedNumber(
      Number.isInteger(version) && version > 0 ? version : null,
    );
  }, [id, search]);
  useEffect(() => {
    let alive = true;
    const load = () =>
      api<RequestDetail>(`${base}/${id}`)
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
  }, [id, base]);
  useEffect(() => {
    if (selectedNumber === null) {
      setSelectedVersion(null);
      return;
    }
    let alive = true;
    api<ResultVersion>(`${base}/${id}/versions/${selectedNumber}`)
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
  }, [id, selectedNumber, base]);
  const loadingVersion =
    selectedNumber !== null && selectedVersion?.number !== selectedNumber;
  const result =
    selectedNumber === null ? value?.latest_version : selectedVersion;
  const ticket =
    loadingVersion || isQuestion ? null : result?.ticket || value?.ticket;
  async function continueDiscussion(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updated = await send<RequestDetail>(`${base}/${id}/continue`, {
          message,
          expected_version: value!.latest_version!.number,
        });
      setValue(updated);
      if (scopeNeedsContext(updated.scope_assessment) && updated.scope_assessment?.operation === "continue") {
        setShowDiscussion(true);
        return;
      }
      router.replace(`${base}/${id}`, { scroll: false });
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
        {error
          ? t(error)
          : t(isQuestion ? "Loading question…" : "Loading request…")}
      </div>
    );
  return (
    <div className="space-y-6">
      <Link
        href={isQuestion ? "/questions" : "/"}
        className="inline-flex items-center gap-2 text-sm muted"
      >
        <ArrowLeft size={16} />{" "}
        {t(isQuestion ? "All questions" : "All requests")}
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-primary">
            {value.environment_name}{" "}
            {t(isQuestion ? "· Question" : "· Request")} {value.id.slice(0, 8)}
          </p>
          <h1>
            {(isQuestion
              ? (!loadingVersion && result?.explanation?.title) || value.title
              : ticket?.title) ||
              t(isQuestion ? "Your question" : "Your request")}
          </h1>
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
      {scopeNeedsContext(value.scope_assessment) && <ScopeAssessmentPanel
        key={`${value.id}-${value.scope_assessment?.operation || "initial"}`}
        value={value}
        base={base}
        disabled={busy}
        onUpdated={(updated) => {
          setValue(updated);
          setError("");
          if (updated.scope_pending_message) {
            setMessage(updated.scope_pending_message);
            setShowDiscussion(true);
          }
        }}
      />}
      <Card>
        <h2>
          {t(isQuestion ? "Your original question" : "Your original need")}
        </h2>
        <p className="mt-3 whitespace-pre-wrap leading-7">{value.original_need || value.messages?.find((item) => item.kind === "need")?.content || value.need}</p>
        {value.original_need && value.original_need !== value.need && <div className="mt-4 rounded-lg bg-muted p-4">
          <h3 className="text-sm">{t("Current formulation")}</h3>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{value.need}</p>
        </div>}
        {value.understanding && (
          <div className="mt-5 rounded-lg bg-muted p-4">
            <h3 className="text-sm">{t("What SpecHelper understood")}</h3>
            <p className="mt-2 text-sm leading-6">{value.understanding}</p>
          </div>
        )}
        {value.attachments.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-3">
            {value.attachments.map((a) => (
              <div key={a.id} className="min-w-0 rounded-md border px-3 py-2">
                <a
                  className="flex items-center gap-1 text-sm text-primary"
                  href={`/api${base}/${id}/attachments/${a.id}`}
                >
                  <Paperclip size={14} />
                  {a.name}
                </a>
                {a.internal && (
                  <p className="mt-1 text-xs muted">
                    {t("Internal Markdown context")}
                  </p>
                )}
                {a.source_question && (
                  <Link
                    className="mt-1 inline-block text-xs text-primary underline"
                    href={`/questions/${a.source_question.id}?version=${a.source_question.version}`}
                  >
                    {t("Source question")} · {t("Version")}{" "}
                    {a.source_question.version}
                  </Link>
                )}
                {value.status === "DRAFT" && (
                  <button
                    className="mt-2 block text-xs text-red-700 underline"
                    disabled={busy}
                    type="button"
                    onClick={async () => {
                      setBusy(true);
                      setError("");
                      try {
                        await api(`${base}/${id}/attachments/${a.id}`, {
                          method: "DELETE",
                        });
                        setValue(await api<RequestDetail>(`${base}/${id}`));
                      } catch (e) {
                        setError((e as Error).message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    {t("Remove attachment {name}", { name: a.name })}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
      {value.source_question && (
        <Card>
          <h2>{t("Source question")}</h2>
          <Link
            className="mt-2 inline-block text-primary underline"
            href={`/questions/${value.source_question.id}?version=${value.source_question.version}`}
          >
            {value.source_question.title || t("Question")} · {t("Version")}{" "}
            {value.source_question.version}
          </Link>
          <p className="mt-2 text-sm muted">
            {t(
              "This request has its own analysis and frozen context. Source conclusions must be checked against its Git references.",
            )}
          </p>
        </Card>
      )}
      {isQuestion && !!value.derived_requests?.length && (
        <Card>
          <h2>{t("Requests created from this question")}</h2>
          <ul className="mt-3 space-y-2">
            {value.derived_requests.map((request) => (
              <li key={request.id}>
                <Link
                  className="text-sm text-primary underline"
                  href={`/requests/${request.id}`}
                >
                  {request.need}
                </Link>
                <span className="ml-2 text-xs muted">
                  {t(statuses[request.status] || request.status)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {active.includes(value.status) && (
        <Card aria-live="polite">
          <h2>
            {["QUEUED", "CONTINUING_CONVERSATION"].includes(value.status)
              ? t(
                  isQuestion
                    ? "Your question is queued"
                    : "Your request is queued",
                )
              : t(
                  isQuestion
                    ? "SpecHelper is exploring your project"
                    : "SpecHelper is preparing your ticket",
                )}
          </h2>
          <p className="mt-2 text-sm muted">
            {["QUEUED", "CONTINUING_CONVERSATION"].includes(value.status)
              ? t(
                  "It will be processed when an assistant is available. Queue time does not reduce analysis time.",
                )
              : t(
                  "The analysis continues until its checks are complete. You can leave this page and return later.",
                )}
          </p>
          {value.analysis_protocol === "2.4" && <div className="mt-3"><AnalysisCancelButton requestId={id} workflow={isQuestion ? "question" : "request"} onCancelled={async () => setValue(await api<RequestDetail>(`${base}/${id}`))} /></div>}
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
      {(value.status === "CANCELLED" || (value.analysis_protocol === "2.4" && value.status === "ERROR")) && <Card>
        <h2>{t(value.status === "CANCELLED" ? "Analysis cancelled" : "Analysis interrupted")}</h2>
        <p className="mt-2 text-sm muted">{t(value.status === "CANCELLED" ? "Execution has stopped. Earlier results and recorded evidence remain available." : "Completed checks and previous results are kept. Only the interrupted step is retried.")}</p>
        {value.analysis_protocol === "2.4" && <div className="mt-4"><AnalysisRetryButton requestId={id} workflow={isQuestion ? "question" : "request"} onRetried={async () => setValue(await api<RequestDetail>(`${base}/${id}`))} /></div>}
      </Card>}
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
            : t("Independent analyses are enabled for this analysis.")}
        </p>
      )}
      {value.status === "DRAFT" && !scopeNeedsContext(value.scope_assessment) && (
        <Card>
          <p className="mb-4">
            {t(
              isQuestion
                ? "This question is saved and ready to start."
                : "This request is saved and ready to start.",
            )}
          </p>
          <Button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                setValue(await send<RequestDetail>(`${base}/${id}/analyze`));
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {t(isQuestion ? "Analyze this question" : "Analyze this request")}
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
                    {m.kind === "result" || m.kind === "error"
                      ? t(m.content)
                      : m.content}
                  </p>
                </div>
              ))}
          </div>
        </details>
      )}
      {value.status === "NEEDS_CLARIFICATION" && (
        <BusinessClarification
          key={JSON.stringify(value.questions)}
          value={value}
          base={base}
          onUpdated={updated => {
            setValue(updated);
            setSelectedNumber(null);
            setSelectedVersion(null);
            router.replace(`${base}/${id}`, { scroll: false });
          }}
        />
      )}
      {!loadingVersion && <BusinessOverview summary={selectedNumber !== null ? result?.business_summary : value.business_summary || result?.business_summary} />}
      {!loadingVersion && <AnalysisEvidence report={selectedNumber !== null ? result?.evidence : value.evidence || result?.evidence} historical={selectedNumber !== null} />}
      {!loadingVersion && <BusinessDecisions
        key={`${id}-${selectedNumber ?? "current"}`}
        value={value}
        result={result}
        historical={selectedNumber !== null}
        base={base}
        onUpdated={updated => {
          setValue(updated);
          if (active.includes(updated.status)) {
            setSelectedNumber(null);
            setSelectedVersion(null);
            setShowDiscussion(false);
            router.replace(`${base}/${id}`, { scroll: false });
          }
        }}
      />}
      {loadingVersion && (
        <p role="status">{t("Loading the selected version…")}</p>
      )}
      {result && !loadingVersion && (result.status === "PARTIAL" || result.status === "ERROR") && <section role="status" className="rounded-xl border border-amber-500/50 bg-card p-5 text-sm" aria-label={t("Result reliability")}>
        <h2 className="text-base">{t(result.status === "PARTIAL" ? "Partial result" : "No usable result")}</h2>
        <p className="mt-2">{t("Execution has ended, but the required independent checks are incomplete. This result is not a fully verified analysis.")}</p>
        {!!result.evidence?.limitations.length && <ul className="mt-3 list-disc space-y-1 pl-5">{result.evidence.limitations.map((limit, index) => <li key={index}>{t(limit)}</li>)}</ul>}
        {!isQuestion && <p className="mt-3 font-medium">{t("Publication is blocked until the required checks are complete. You can still review the draft and download the artifacts.")}</p>}
      </section>}
      {isQuestion && result && !loadingVersion && (
        <QuestionResult
          key={`${id}-${result.number}`}
          questionId={id}
          onContinue={() => setShowDiscussion(true)}
          discussionAvailable={!value.validated_version && ["READY", "PARTIAL", "ERROR"].includes(value.status)}
          result={result}
          versions={value.versions}
          latestNumber={value.latest_version?.number}
          selectedNumber={selectedNumber}
          onSelect={(number) => {
            router.replace(
              `${base}/${id}${number === null ? "" : `?version=${number}`}`,
              { scroll: false },
            );
            setSelectedVersion(null);
            setSelectedNumber(number);
          }}
        />
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
                      router.replace(
                        `${base}/${id}${e.target.value === "latest" ? "" : `?version=${e.target.value}`}`,
                        { scroll: false },
                      );
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
                      .filter(
                        (v) =>
                          v.number !== value.latest_version?.number ||
                          v.number === selectedNumber,
                      )
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
              {result && !loadingVersion && (
                <PublishTicket requestId={id} version={result.number} />
              )}
              <Button variant="outline" onClick={copy}>
                <Copy size={16} />
                {copied ? t("Copied!") : t("Copy for Jira")}
              </Button>
              <Button asChild>
                <a
                  href={
                    result?.artifacts["ticket.md"] ||
                    `/api${base}/${id}/markdown`
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
            {result && (
              <AnalysisContext
                workflow={workflow}
                requestId={id}
                runNumber={result.run_number}
                snapshot={result.context_snapshot}
                usage={result.context_usage}
              />
            )}
            {Object.entries(
              ticket.need !== undefined || result?.format_version === "1.2"
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
        ["READY", "PARTIAL", "ERROR"].includes(value.status) &&
        !value.validated_version &&
        !(scopeNeedsContext(value.scope_assessment) && value.scope_assessment?.operation === "continue") &&
        (!isQuestion || showDiscussion) && (
          <Card id="discussion">
            <h2>
              {t(
                isQuestion
                  ? "Explore this explanation further"
                  : "Refine this proposal",
              )}
            </h2>
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
                    {busy
                      ? t("Sending…")
                      : t(
                          isQuestion
                            ? "Send and update explanation"
                            : "Send and update proposal",
                        )}
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
      {!!value.analysis_runs?.length && (
        <Card>
          <details
            open={value.analysis_runs.some(
              (run) =>
                !!run.warnings?.length ||
                run.steps.some((step) => !!step.warnings?.length),
            )}
          >
            <summary className="cursor-pointer text-sm font-semibold">
              {t("Analysis assignment history")}
            </summary>
            <div className="mt-4 space-y-4">
              {value.analysis_runs.map((run) => (
                <div key={run.number}>
                  <h3 className="text-sm">
                    {t("Analysis")} {run.number} ·{" "}
                    {t(statuses[run.status] || run.status)}
                  </h3>
                  <AnalysisContext
                    workflow={workflow}
                    requestId={id}
                    runNumber={run.number}
                    snapshot={run.context_snapshot}
                    usage={run.context_usage}
                  />
                  {!!run.warnings?.length && (
                    <ul
                      className="mt-2 space-y-1 text-sm text-amber-800"
                      aria-label={t("Analysis warnings")}
                    >
                      {run.warnings.map((warning, index) => (
                        <li key={index}>{t(warningMessage(warning))}</li>
                      ))}
                    </ul>
                  )}
                  <ol className="mt-2 space-y-2 text-sm">
                    {run.steps.map((step, index) => (
                      <li key={index} className="rounded border p-3">
                        <p className="break-words">
                          {t("Step {number}", { number: index + 1 })} ·{" "}
                          {step.public_role &&
                            `${t(roleLabels[step.public_role] || step.public_role)} · `}
                          {step.connection_name || t("AI not assigned")} ·{" "}
                          {step.provider || step.agent || t("Unknown")} ·{" "}
                          {!step.model || step.model === "runtime-default"
                            ? t("Provider default model")
                            : step.model}
                          {step.status &&
                            ` · ${t(statuses[step.status] || step.status)}`}
                        </p>
                        {step.model_family && (
                          <p className="mt-1 text-xs muted">
                            {t("Model family")}: {step.model_family}
                          </p>
                        )}
                        {step.instruction_snapshot && <details className="mt-3 rounded border p-3 text-xs">
                          <summary className="cursor-pointer font-medium">{t("Recorded execution configuration")}</summary>
                          <p className="mt-2 muted">{t("These instructions belong to this step. Later settings changes do not replace them.")}</p>
                          <h4 className="mt-3 font-medium">{t("Global instructions")}{step.instruction_snapshot.global_instruction_version !== undefined && ` · v${step.instruction_snapshot.global_instruction_version}`}</h4>
                          <p className="mt-1 whitespace-pre-wrap break-words">{step.instruction_snapshot.global_instructions || t("None")}</p>
                          <h4 className="mt-3 font-medium">{t("Specific instructions")}</h4>
                          <p className="mt-1 whitespace-pre-wrap break-words">{step.instruction_snapshot.connection_instructions?.additional_instructions || t("None")}</p>
                          {step.instruction_snapshot.connection_instructions?.version && <p className="mt-1 break-all muted">SHA-256: {step.instruction_snapshot.connection_instructions.version}</p>}
                          <h4 className="mt-3 font-medium">{t("Skills actually loaded")}</h4>
                          {step.skills_audit === "observed" ? step.loaded_skills?.length ? <ul className="mt-2 space-y-2">{step.loaded_skills.map(skill => <li key={`${skill.slug}:${skill.version}`} className="break-words">{skill.name || skill.slug} · v{skill.version}{skill.sha256 && <span className="mt-1 block break-all muted">SHA-256: {skill.sha256}</span>}</li>)}</ul> : <p className="mt-1 muted">{t("No skill-content read was observed during this step.")}</p> : <p className="mt-1 muted">{t("Skill read telemetry is unavailable. Available skills are not evidence of use.")}</p>}
                        </details>}
                        {!!step.warnings?.length && (
                          <ul
                            className="mt-2 space-y-1 text-amber-800"
                            aria-label={t("Analysis warnings")}
                          >
                            {step.warnings.map((warning, warningIndex) => (
                              <li key={warningIndex}>
                                {t(warningMessage(warning))}
                              </li>
                            ))}
                          </ul>
                        )}
                        {!!step.conclusions?.length && (
                          <ul
                            className="mt-2 list-disc pl-5"
                            aria-label={t("Verifiable conclusions")}
                          >
                            {step.conclusions.map(
                              (conclusion, conclusionIndex) => (
                                <li key={conclusionIndex}>{conclusion}</li>
                              ),
                            )}
                          </ul>
                        )}
                        {(step.failure || step.error) && (
                          <p className="mt-1 text-red-700">
                            {t(
                              step.diagnostic ||
                                statuses[step.failure || ""] ||
                                step.failure ||
                                step.error ||
                                "",
                            )}
                          </p>
                        )}
                      </li>
                    ))}
                  </ol>
                  {run.error && (
                    <p className="mt-2 text-sm text-red-700">{t(run.error)}</p>
                  )}
                </div>
              ))}
            </div>
          </details>
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
                {r.path || r.repository} · {r.branch}
              </p>
              {r.connection_name && (
                <p className="mt-1 muted">{r.connection_name}</p>
              )}
              {r.is_fork && (
                <p className="mt-1 muted">
                  {t("Fork")}
                  {r.parent?.path
                    ? ` · ${t("Parent repository")}: ${r.parent.path}`
                    : ""}
                </p>
              )}
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
