"use client";
import { BusinessClarification, BusinessDecisions, BusinessOverview } from "@/components/business-clarification";
import { QuestionResult } from "@/components/question-result";
import { PublishTicket } from "@/components/publish-ticket";
import { AnalysisContext } from "@/components/analysis-context";
import { AnalysisEvidence } from "@/components/analysis-evidence";
import { AnalysisCancelButton } from "@/components/analysis-cancel-button";
import { AnalysisRetryButton } from "@/components/analysis-retry-button";
import { AnalysisDeleteButton } from "@/components/analysis-delete-button";
import { AIReportDownloads } from "@/components/ai-report-downloads";
import { ScopeAssessmentPanel } from "@/components/scope-assessment";
import { NeedEditor } from "@/components/need-editor";
import { AnalysisConversation, conversationAnswer } from "@/components/analysis-timeline";
import { DiscussionComposer } from "@/components/discussion-composer";
import { AnalysisDiagrams } from "@/components/analysis-diagrams";
import { useI18n } from "@/lib/i18n";
import { modelFamilyDiversity, roleLabels, warningMessage } from "@/lib/orchestration";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Copy,
  Download,
  Paperclip,
  Send,
  FileText,
  Pencil,
  ChevronDown,
  MessageSquare,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  api,
  send,
  statuses,
  scopeNeedsContext,
  type RequestDetail,
  type ResultVersion,
  type WorkUpdate,
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
  unified?: boolean;
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
  unified = false,
}: {
  params: Promise<{ id: string }>;
  workflow?: "request" | "question";
  unified?: boolean;
}) {
  const { t, dateLocale } = useI18n();
  const { id } = use(params);
  const search = useSearchParams();
  const router = useRouter();
  const [value, setValue] = useState<RequestDetail | null>(null);
  const isQuestion = (unified ? value?.workflow : workflow) === "question";
  const base = isQuestion ? "/questions" : "/requests";
  const detailBase = unified ? "/analyses" : base;
  const [selectedVersion, setSelectedVersion] = useState<ResultVersion | null>(
    null,
  );
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [trackingUnavailable,setTrackingUnavailable]=useState(false);
  const latestValue=useRef<RequestDetail|null>(null);
  useEffect(()=>{latestValue.current=value;},[value]);
  const pollingActive=!!value&&active.includes(value.status);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  useEffect(() => { setEditingTitle(false); setTitleDraft(""); }, [id]);
  const [goalCopied, setGoalCopied] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (value?.scope_pending_message) {
      setMessage((current) => current || value.scope_pending_message || "");
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
    let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      const before=latestValue.current?.id===id ? latestValue.current : null;
      try {
        if(before?.progress_token){
          const update=await api<WorkUpdate>(`/analyses/${id}/progress?cursor=${encodeURIComponent(before.progress_cursor||"")}`,{signal:AbortSignal.timeout(15000)});
          if(!alive)return;
          if(update.unchanged){setTrackingUnavailable(false);return;}
          if(update.progress_token===before.progress_token){
            setValue(current=>current&&current.progress_token===before.progress_token ? {...current,work_progress:update.work_progress,progress_cursor:update.progress_cursor} : current);
            setTrackingUnavailable(false);return;
          }
        }
        const fresh=await api<RequestDetail>(`${unified ? "/analyses" : base}/${id}`,{signal:AbortSignal.timeout(15000)});
        if(alive){setValue(current=>!before || current?.progress_token===before.progress_token ? fresh : current);setError("");setTrackingUnavailable(false);}
      } catch(failure){if(alive){setTrackingUnavailable(true);if(!before)setError((failure as Error).message);}}
      finally {if(alive)timer=setTimeout(poll,before?.progress_token&&!active.includes(before.status) ? 10000 : 2000);}
    };
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id, base, unified,pollingActive]);
  useEffect(() => {
    if (unified && (!value || value.id !== id)) return;
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
  }, [id, selectedNumber, base, unified, value?.id, value?.workflow]);
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
        return;
      }
      router.replace(`${detailBase}/${id}`, { scroll: false });
      setMessage("");
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
  async function copyAnswer() {
    try {
      await navigator.clipboard.writeText(result ? conversationAnswer(result) || result.answer_markdown || result.markdown : "");
      setCopied(true); setTimeout(() => setCopied(false), 2500);
    } catch { setError(t("Copying is unavailable in this browser. Download the Markdown instead.")); }
  }
  if (!value || value.id !== id)
    return (
      <div role={error ? "alert" : "status"}>
        {error
          ? t(error)
          : t("Loading analysis…")}
      </div>
    );
  const titleLocked = busy || ["QUEUED", "UNDERSTANDING", "ANALYZING", "REVIEWING", "GENERATING_RESULT", "CONTINUING_CONVERSATION", "GENERATING_TICKET"].includes(value.status);
  function selectConversationVersion(number: number) {
    router.replace(`${detailBase}/${id}?version=${number}`, { scroll: false });
    setSelectedVersion(null); setSelectedNumber(number);
  }
  function openReport() {
    setReportOpen(true);
    requestAnimationFrame(() => { const report = document.getElementById("analysis-report"); report?.scrollIntoView({block:"start", behavior:"smooth"}); report?.querySelector("summary")?.focus(); });
  }
  const conversationReply = (unified || value.discussion?.enabled) && value.status !== "NEEDS_CLARIFICATION" && !scopeNeedsContext(value.scope_assessment) ? <DiscussionComposer value={value} onUpdated={updated=>{setValue(updated);setSelectedNumber(null);setSelectedVersion(null);}}/> : <>
      {active.includes(value.status) && <div className="conversation-composer"><label className="sr-only" htmlFor="pending-followup">{t("Your message")}</label><Textarea id="pending-followup" rows={1} disabled placeholder={t("You can reply when the investigation pauses or finishes.")} /></div>}
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
          }
        }}
      />}
      {value.status === "NEEDS_CLARIFICATION" && (
        <BusinessClarification
          conversational
          key={JSON.stringify(value.questions)}
          value={value}
          base={base}
          onUpdated={updated => {
            setValue(updated);
            setSelectedNumber(null);
            setSelectedVersion(null);
            router.replace(`${detailBase}/${id}`, { scroll: false });
          }}
        />
      )}
      {value.latest_version &&
        ["READY", "PARTIAL", "ERROR"].includes(value.status) &&
        !value.validated_version &&
        !(scopeNeedsContext(value.scope_assessment) && value.scope_assessment?.operation === "continue") &&
        <Card id="discussion" className="conversation-composer">
            {selectedNumber !== null && <p className="mb-3 text-xs muted">{t("The discussion continues from the latest version (v")}{value.latest_version.number}).</p>}
            <form onSubmit={continueDiscussion} className="conversation-compose-form">
                <MessageSquare className="conversation-compose-icon" size={20} aria-hidden="true" />
                <div className="field">
                  <label className="sr-only" htmlFor="followup">{t("Your message")}</label>
                  <Textarea
                    id="followup"
                    required
                    minLength={1}
                    maxLength={30000}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder={t("Reply or add a detail…")}
                    rows={1}
                    onKeyDown={event=>{
                      if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                        event.preventDefault();
                        if (!busy && message.trim()) event.currentTarget.form?.requestSubmit();
                      }
                    }}
                  />
                </div>
                <div className="conversation-compose-actions">
                  <Button disabled={busy || !message.trim()} className="conversation-send" title={t("Send message")}>
                    <Send size={21} aria-hidden="true" /><span className="sr-only">{busy
                      ? t("Sending…")
                      : t(
                          isQuestion
                            ? "Send and update explanation"
                            : "Send and update proposal",
                        )}</span>
                  </Button>
                  {message && <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setMessage("")}
                  >
                    <X size={17} aria-hidden="true" /><span className="sr-only">{t("Cancel")}</span>
                  </Button>}
                </div>
              </form>
          </Card>
        }
  </>;
  return (
    <div className="analysis-conversation-page space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3"><Link
        href="/analyses"
        className="inline-flex items-center gap-2 text-sm muted"
      >
        <ArrowLeft size={16} />{" "}
        {t("All analyses")}
      </Link>
      <AnalysisDeleteButton id={id} title={value.title || value.need.split("\n")[0]} disabled={busy || active.includes(value.status)} /></div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-primary">
            {value.environment_name}{" "}
            {t(value.intent_mode === "auto" && !value.understanding && !value.latest_version ? "· Analysis" : isQuestion ? "· Question" : "· Change")} {value.id.slice(0, 8)}
          </p>
          <h1 className="break-words">{value.title || value.need.split("\n")[0] || t("Analysis")}</h1>
          {editingTitle ? <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={async event => {
            event.preventDefault(); setBusy(true); setError("");
            try { const renamed = await send<{ title: string }>(`/analyses/${value.id}/title`, { title: titleDraft }, "PATCH"); setValue({ ...value, title: renamed.title }); setEditingTitle(false); requestAnimationFrame(() => document.getElementById("edit-analysis-title")?.focus()); window.dispatchEvent(new Event("queue-updated")); }
            catch (failure) { setError((failure as Error).message); }
            finally { setBusy(false); }
          }}>
            <label className="min-w-0 flex-1 text-sm" htmlFor="analysis-title">{t("Analysis title")}<Input id="analysis-title" autoFocus className="mt-1" maxLength={160} required value={titleDraft} onChange={event => setTitleDraft(event.target.value)} /></label>
            <Button size="sm" disabled={titleLocked}>{t("Save title")}</Button>
            <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => { setEditingTitle(false); requestAnimationFrame(() => document.getElementById("edit-analysis-title")?.focus()); }}>{t("Cancel")}</Button>
          </form> : <Button id="edit-analysis-title" className="conversation-title-edit" aria-label={t("Edit title")} type="button" size="sm" variant="ghost" disabled={titleLocked} title={titleLocked ? t("Wait for the analysis to finish before renaming it.") : t("Edit title")} onClick={() => { setTitleDraft(value.title || value.need.split("\n")[0]); setEditingTitle(true); }}><Pencil size={14} aria-hidden="true" /></Button>}
        </div>
      </div>
      {(error || value.error) && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"
        >
          {error ? t(error) : value.discussion?.mode === "discussion" ? t(value.error) : t("The analysis was interrupted. Open diagnostics for details.")}
          {value.error && value.discussion?.mode !== "discussion" && <details className="mt-2"><summary className="cursor-pointer">{t("Diagnostics")}</summary><pre className="mt-2 whitespace-pre-wrap break-words text-xs">{value.error}</pre></details>}
        </div>
      )}
      <AnalysisConversation value={value} result={loadingVersion ? null : result} trackingUnavailable={trackingUnavailable}
        reply={conversationReply} onSelectVersion={selectConversationVersion}
        actions={<>
          <Button variant="outline" size="sm" onClick={openReport}>{t("Analysis report")}</Button>
          {!isQuestion && result && !value.conclusions_stale && <PublishTicket requestId={id} version={result.number} />}
          {isQuestion && result && !value.conclusions_stale && <Button asChild size="sm"><Link href={`/analyses?new=1&from_question=${id}&version=${result.number}`}>{t("Prepare a change")}</Link></Button>}
          <Button variant="ghost" size="sm" onClick={copyAnswer}><Copy size={14} aria-hidden="true" />{t(copied ? "Copied!" : "Copy answer")}</Button>
        </>}
        controls={<>
          {!unified && !value.discussion?.enabled && value.analysis_protocol === "2.4" && active.includes(value.status) && <AnalysisCancelButton requestId={id} workflow={isQuestion ? "question" : "request"} onCancelled={async () => setValue(await api<RequestDetail>(`${base}/${id}`))} />}
          {!unified && !value.discussion?.enabled && value.analysis_protocol === "2.4" && ["ERROR","CANCELLED"].includes(value.status) && <AnalysisRetryButton requestId={id} workflow={isQuestion ? "question" : "request"} onRetried={async () => setValue(await api<RequestDetail>(`${base}/${id}`))} />}
        </>}
      />
      {loadingVersion && <p role="status">{t("Loading the selected version…")}</p>}
      {!unified && !value.discussion?.enabled && value.status === "DRAFT" && !scopeNeedsContext(value.scope_assessment) && (
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
      {result && <details id="analysis-report" className="conversation-report" open={reportOpen} onToggle={event=>setReportOpen(event.currentTarget.open)}>
        <summary className="conversation-report-summary"><span className="conversation-report-icon"><FileText size={27} aria-hidden="true" /></span><span className="min-w-0 flex-1"><span className="flex flex-wrap items-center gap-3"><strong>{t("Final synthesis")}</strong><span className="badge">{t(result ? result.status === "ERROR" ? "No usable result" : result.status === "READY" && !result.evidence?.blocking ? "Result available" : "Partial result" : "Upcoming")}</span></span><span className="mt-1 block text-sm muted">{t(result ? "Analysis report and deliverables" : "Conclusions and deliverables will appear after the investigation.")}</span></span><ChevronDown size={19} aria-hidden="true" /></summary>
        {reportOpen && <div className="mt-5 space-y-6">
      <p className="text-xs muted">{t(modelFamilyDiversity(value.analysis_runs?.find(run=>run.number === result.run_number)?.steps))}</p>
      {result && !loadingVersion && <AIReportDownloads value={value} result={result} />}
      {value.conclusions_stale && <section role="status" className="rounded-xl border border-amber-500/50 bg-card p-5">
        <h2 className="text-base">{t("Previous conclusions need reassessment")}</h2>
        <p className="mt-2 text-sm">{t("The need has changed. Previous results remain available as history and cannot be published as the current analysis.")}</p>
      </section>}
      {!loadingVersion && <BusinessOverview summary={selectedNumber !== null ? result?.business_summary : value.business_summary || result?.business_summary} />}
      {!loadingVersion && <AnalysisDiagrams diagrams={(selectedNumber !== null ? result?.evidence : result?.evidence || value.evidence)?.diagrams} />}
      <Card>
        <h2>
          {t(isQuestion ? "Your original question" : "Your original need")}
        </h2>
        <p className="mt-3 whitespace-pre-wrap leading-7">{value.original_need || value.messages?.find((item) => item.kind === "need")?.content || value.need}</p>
        <NeedEditor value={value} onUpdated={updated => { setValue(updated); setSelectedNumber(null); setSelectedVersion(null); }} />
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
          <h2>{t("Analyses created from this question")}</h2>
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
      {!loadingVersion && (result?.evidence || value.evidence) && <details className="rounded-xl border bg-card p-5"><summary className="cursor-pointer font-medium">{t("Verification details")}</summary><div className="mt-4"><AnalysisEvidence report={selectedNumber !== null ? result?.evidence : value.evidence || result?.evidence} historical={selectedNumber !== null} /></div></details>}
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
                  router.replace(`${detailBase}/${id}`, { scroll: false });
          }
        }}
      />}
      {loadingVersion && (
        <p role="status">{t("Loading the selected version…")}</p>
      )}
      {result && !loadingVersion && (result.status === "PARTIAL" || result.status === "ERROR" || result.evidence?.blocking) && <section role="status" className="rounded-xl border border-amber-500/50 bg-card p-5 text-sm" aria-label={t("Result reliability")}>
        <h2 className="text-base">{t(result.status === "ERROR" ? "No usable result" : "Partial result")}</h2>
        <p className="mt-2">{t("Execution has ended, but the required independent checks are incomplete. This result is not a fully verified analysis.")}</p>
        {!!result.evidence?.limitations?.length && <ul className="mt-3 list-disc space-y-1 pl-5">{result.evidence.limitations.map((limit, index) => <li key={index}>{t(limit)}</li>)}</ul>}
        {!isQuestion && <p className="mt-3 font-medium">{t("Publication is blocked until the required checks are complete. You can still review the draft and download the artifacts.")}</p>}
      </section>}
      {isQuestion && result && !loadingVersion && (
        <QuestionResult
          key={`${id}-${result.number}`}
          questionId={id}
          onContinue={() => document.getElementById("followup")?.focus()}
          discussionAvailable={!value.validated_version && ["READY", "PARTIAL", "ERROR"].includes(value.status)}
          result={result}
          versions={value.versions}
          latestNumber={value.latest_version?.number}
          selectedNumber={selectedNumber}
          onSelect={(number) => {
            router.replace(
              `${detailBase}/${id}${number === null ? "" : `?version=${number}`}`,
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
                        `${detailBase}/${id}${e.target.value === "latest" ? "" : `?version=${e.target.value}`}`,
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
      {!!value.analysis_runs?.length && (
        <Card>
          <details id="analysis-provenance">
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
        </div>}
      </details>}
    </div>
  );
}
