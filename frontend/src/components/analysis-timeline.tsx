"use client";

import Link from "next/link";
import { type ReactNode } from "react";
import { Sparkles, Folder, CalendarDays, ChevronDown, LoaderCircle, CheckCircle2, Clock3, CircleHelp, AlertCircle, Circle, MessageCircle } from "lucide-react";
import { SafeMarkdown } from "@/components/safe-markdown";
import { RoleMentions } from "@/components/role-mentions";
import { Button } from "@/components/ui/button";
import { type RequestDetail, type ResultVersion, resultStates, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { roleLabels } from "@/lib/orchestration";
import { useInstanceName } from "@/lib/instance";

type Run = NonNullable<RequestDetail["analysis_runs"]>[number];

type Event = {
  id: string; at: string; speaker: "user" | "assistant"; content: string; label?: string;
  version?: number; child?: string; url?: string; sortAt?: number;
  run?: Run;
  markdown?: boolean;
  discussion?: boolean;
};

export function AnalysisConversation({ value, result, reply, actions, controls, onSelectVersion }: {
  value: RequestDetail; result?: ResultVersion | null; reply?: ReactNode;
  actions?: ReactNode; controls?: ReactNode; onSelectVersion?: (version: number) => void;
}) {
  const { t, dateLocale } = useI18n();
  const instanceName = useInstanceName();
  const runs = value.analysis_runs || [];
  const working = ["QUEUED", "UNDERSTANDING", "ANALYZING", "REVIEWING", "GENERATING_TICKET", "GENERATING_RESULT", "CONTINUING_CONVERSATION"].includes(value.status);
  const pending = value.status === "NEEDS_CLARIFICATION";
  const messages = value.messages || [];
  const lastClarification = messages.filter(message => ["questions", "clarification"].includes(message.kind)).at(-1);
  const pendingMessage = pending && lastClarification?.content === value.questions.map(question=>question.question).join("\n") ? lastClarification : undefined;
  const events: Event[] = messages.filter(message => {
    if (["result", "decision_revision", "error"].includes(message.kind)) return false;
    // Pending questions appear once, together with their real answer controls.
    return message.id !== pendingMessage?.id;
  }).map(message => {
    const answers = message.data?.answers;
    return { id: `message-${message.id}`, at: message.created_at,
      speaker: message.role === "user" ? "user" : "assistant",
      content: answers && typeof answers === "object" ? Object.values(answers).filter(item => typeof item === "string").join("\n\n") : message.content,
      label: message.kind === "need_revision" ? "Need updated" : undefined,
      markdown: message.kind === "discussion_reply",
      child: typeof message.data?.child_id === "string" ? message.data.child_id : undefined };
  });
  if (!messages.some(message => message.kind === "need")) events.unshift({ id: "original", at: value.created_at,
    speaker: "user", content: value.original_need || value.need });
  // Early installations retained Q&A only in the business conversation ledger.
  if (!messages.some(message => ["answer", "answers", "clarification", "questions"].includes(message.kind))) {
    (value.conversation || []).forEach((turn, index) => {
      events.push({id:`legacy-question-${index}`, at:value.created_at, speaker:"assistant", content:turn.questions.map(question=>question.question).join("\n\n")});
      events.push({id:`legacy-answer-${index}`, at:value.created_at, speaker:"user", content:Object.values(turn.answers).join("\n\n")});
    });
  }
  const versions = [...(value.versions || [])];
  for (const available of [value.latest_version, result]) {
    if (available && !versions.some(version=>version.number === available.number)) versions.push(available);
  }
  for (const version of versions) {
    const message = messages.find(message => message.kind === "result" && message.version_number === version.number);
    const displayed = version.number === result?.number ? result : version.number === value.latest_version?.number ? value.latest_version : null;
    const summary = displayed ? conversationAnswer(displayed) : message?.data?.summary;
    events.push({ id: `result-${version.number}`, at: version.created_at, speaker: "assistant", version: version.number,
      content: typeof summary === "string" ? summary : "", label: version.status === "PARTIAL" || version.status === "ERROR" || displayed?.evidence?.blocking ? "Partial result" : "Result available" });
  }
  for (const publication of value.publications || []) events.push({ id:`publication-${publication.id}`, at:publication.created_at, speaker:"assistant", content:publication.title,
    label:publication.status === "PUBLISHED" ? "Ticket published" : publication.status === "ERROR" ? "Ticket publication failed" : "Ticket publication not confirmed",
    url:publication.status === "PUBLISHED" && /^https?:\/\//i.test(publication.url) ? publication.url : undefined });
  for (const run of runs) {
    const at=run.started_at || run.steps.find(step=>step.started_at)?.started_at || value.created_at;
    const start=new Date(at).getTime();
    const end=run.finished_at ? new Date(run.finished_at).getTime() : run.number === Math.max(...runs.map(run=>run.number)) ? Infinity : start;
    const latestInput=Math.max(start,...events.filter(event=>event.speaker === "user").map(event=>new Date(event.at).getTime()).filter(time=>time >= start && time <= end));
    // Position resumed work after its input; keep actual timestamps unchanged.
    events.push({id:`progress-${run.number}`,at,sortAt:latestInput + 1,speaker:"assistant",content:"",run});
  }
  if (!runs.length && (working || pending) && value.discussion?.mode !== "discussion") events.push({id:"progress-pending",at:value.created_at,sortAt:Math.max(new Date(value.created_at).getTime(),...events.filter(event=>event.speaker === "user").map(event=>new Date(event.at).getTime()))+1,speaker:"assistant",content:"",run:{number:0,status:value.status,steps:[]}});
  if (value.discussion?.mode === "discussion" && value.discussion.job && ["QUEUED","RUNNING"].includes(value.discussion.job.status)) events.push({
    id:`discussion-progress-${value.discussion.revision}`,at:value.discussion.job.created_at,speaker:"assistant",content:"",discussion:true,
    label:value.discussion.job.status === "RUNNING" ? "The assistant is replying…" : value.discussion.job.waiting_reason ? "Waiting for the selected AI connection." : "In queue",
  });
  events.sort((left, right) => (left.sortAt ?? new Date(left.at).getTime()) - (right.sortAt ?? new Date(right.at).getTime()));

  return <section className="analysis-conversation" aria-label={t("Business conversation")}>
    <div className="conversation-toolbar">
      <div className="conversation-metadata"><span><Folder size={17} aria-hidden="true" />{t("Business conversation")}</span><time dateTime={value.created_at}><CalendarDays size={17} aria-hidden="true" />{new Date(value.created_at).toLocaleString(dateLocale)}</time><span role="status" className="badge conversation-state" data-state={value.status}>{t(resultStates[value.result_state || ""] || statuses[value.status] || value.status)}</span></div>
    </div>
    <ol className="conversation-messages">
      {events.map(event => <li key={event.id} className={`conversation-message conversation-${event.speaker}`} data-message={event.id}>
        {event.speaker === "assistant" && <div className="conversation-avatar conversation-brand-avatar" aria-hidden="true"><Sparkles size={25} /></div>}
        <article className="conversation-bubble">
          {!event.run && <header className="mb-2 flex flex-wrap items-center gap-2 text-sm">
            {value.discussion?.enabled && event.speaker === "assistant" && <strong className="text-sm">{instanceName}</strong>}
            <time dateTime={event.at} className="ml-auto text-xs muted">{new Date(event.at).toLocaleString(dateLocale)}</time>
          </header>}
          {event.run && <InvestigationProgress run={event.run} />}
          {event.label && <p className="mb-2 flex items-center gap-2 text-xs font-medium text-primary">{event.discussion && <LoaderCircle size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true"/>}{t(event.label)}{event.version ? ` · v${event.version}` : ""}</p>}
          {event.content && (event.version || event.markdown ? <div className="conversation-answer break-words text-sm leading-7"><SafeMarkdown roleMentions>{event.content}</SafeMarkdown></div> : <p className="conversation-message-text whitespace-pre-wrap break-words text-sm leading-7">{event.speaker === "assistant" ? <RoleMentions>{event.content}</RoleMentions> : event.content}</p>)}
          {event.child && <Link className="mt-3 inline-block text-sm text-primary underline" href={`/analyses/${event.child}`}>{t("Open linked change")}</Link>}
          {event.url && <a className="mt-3 inline-block text-sm text-primary underline" href={event.url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{t("Open published ticket")}</a>}
          {event.version && event.version !== result?.number && <Button variant="ghost" size="sm" className="mt-3" onClick={()=>onSelectVersion?.(event.version!)}>{t("Read result version {number}", {number:event.version})}</Button>}
          {event.version === result?.number && result && <>
            {value.conclusions_stale && <p className="mt-3 text-sm font-medium">{t("Previous conclusions need reassessment")}</p>}
            {(result.status !== "READY" || result.evidence?.blocking) && <p className="mt-3 text-sm muted">{t("Some conclusions remain unverified. See the analysis report for the limits and evidence.")}</p>}
            {value.discussion?.enabled && result.evidence?.blocking && !!result.evidence.limitations?.length && <ul className="mt-2 list-disc pl-5 text-sm muted">{[...new Set(result.evidence.limitations)].slice(0,3).map(limit=><li key={limit}>{limit}</li>)}</ul>}
            <div className="mt-5 flex flex-wrap gap-2">{actions}</div>
          </>}
        </article>
      </li>)}
    </ol>
    <div className={`conversation-reply ${pending ? "conversation-pending conversation-assistant" : ""}`}>
      {pending && <><div className="conversation-avatar conversation-brand-avatar" aria-hidden="true"><Sparkles size={25} /></div><header className="conversation-pending-author">{value.discussion?.enabled && <strong>{instanceName}</strong>}{pendingMessage && <time dateTime={pendingMessage.created_at}>{new Date(pendingMessage.created_at).toLocaleString(dateLocale)}</time>}</header></>}
      <div className="conversation-reply-content">{reply}</div>
    </div>
    {controls && <div className="flex flex-wrap gap-2">{controls}</div>}
  </section>;
}

export function conversationAnswer(result:ResultVersion) {
  // Display the accepted synthesis, never a concatenation of preliminary agent reports.
  const summary=result.explanation?.summary || result.ticket?.proposed_solution || result.ticket?.context;
  if (typeof summary === "string" && summary.trim()) return summary.trim();
  const explanation = result.explanation?.business_explanation;
  return typeof explanation === "string" ? explanation.trim() : "";
}

const stageLabels:Record<string,string>={done:"Completed",running:"In progress",waiting:"Upcoming",blocked:"AI unavailable",clarification:"Clarification requested",error:"Technical failure",cancelled:"Analysis cancelled",unknown:"Stage completion not recorded"};
const causeLabels:Record<string,string>={quota:"Quota exhausted",busy:"Assistant busy",connection_missing:"No authenticated connection",model_unavailable:"Model unavailable",unavailable:"Unavailable"};

function InvestigationProgress({run}:{run:Run}) {
  const {t}=useI18n();
  const snapshot=run.execution;
  const status=snapshot?.status || run.status;
  const running=!["READY","PARTIAL","ERROR","CANCELLED","NEEDS_CLARIFICATION"].includes(status) ? run.steps.filter(step=>step.status === "RUNNING").at(-1)?.public_role : undefined;
  const current=snapshot?.current_role || running;
  const checkpoints:Record<string,string>={analyst:"analyst",counter_analyst:"comparison",verifier:"verifier"};
  const stages=snapshot?.stages || ["analyst","counter_analyst","verifier"].map(role=>({role,status:running === role ? "running" : run.role_reviews?.some(item=>item.checkpoint === checkpoints[role]) ? "done" : ["READY","PARTIAL","ERROR","CANCELLED"].includes(status) ? "unknown" : "waiting"}));
  const allDone=snapshot?.all_stages_done ?? stages.every(stage=>stage.status === "done");
  const drafting=snapshot?.checkpoint === "writer";
  const terminal=["READY","PARTIAL"].includes(status);
  const active=!["READY","PARTIAL","ERROR","CANCELLED","NEEDS_CLARIFICATION","QUEUED"].includes(status);
  const waiting=status === "QUEUED" && !!snapshot?.waiting_reason;
  const clarification=status === "NEEDS_CLARIFICATION";
  const subtitle=drafting && waiting ? "The three stages have finished. The final response will be drafted when an assistant is available." : drafting && active ? "The three stages have finished. The final response is being prepared." : clarification ? "A business clarification is needed before continuing." : waiting ? current === "counter_analyst" ? "The counter-analysis will resume when an assistant is available." : current === "verifier" ? "Verification will resume when an assistant is available." : "The analysis will resume when an assistant is available." : active ? current === "counter_analyst" ? "Counter-analysis in progress…" : current === "verifier" ? "Verification in progress…" : "Investigation in progress…" : terminal && allDone ? "All three stages have finished." : "";
  const StatusIcon=active ? LoaderCircle : waiting ? Clock3 : clarification ? MessageCircle : terminal && allDone ? CheckCircle2 : CircleHelp;
  const headline=status === "NEEDS_CLARIFICATION" ? "Needs clarification" : status === "ERROR" ? "Analysis interrupted" : status === "CANCELLED" ? "Analysis cancelled" : terminal ? allDone ? "Investigation finished" : "Investigation finished · verification incomplete" : status === "QUEUED" ? snapshot?.waiting_reason ? "Waiting for an AI resource" : "In queue" : current === "counter_analyst" ? "Counter-analysis in progress…" : current === "verifier" ? "Verification in progress…" : "Analysis in progress";
  return <details className="investigation-progress" data-cycle={run.number || "pending"}>
    <summary><StatusIcon size={20} className={active ? "investigation-active animate-spin motion-reduce:animate-none" : clarification ? "investigation-attention" : terminal && allDone ? "text-emerald-600 dark:text-emerald-400" : "muted"} aria-hidden="true" /><span className="investigation-heading" role="status"><span>{t(drafting && waiting ? "Final response awaiting an assistant" : drafting && active ? "Preparing final response…" : active ? "Analysis in progress" : waiting ? "Waiting for an available assistant" : headline)}</span>{subtitle && <span className="investigation-subtitle">{t(subtitle)}</span>}</span>{status === "PARTIAL" && <span className="badge">{t("Partial result")}</span>}<ChevronDown size={16} className="investigation-disclosure" aria-hidden="true" /></summary>
    <div className="investigation-content space-y-4">
      <ol className="investigation-stages" aria-label={t("Investigation stages")}>{stages.map(stage=>{
        const causes = !drafting && stage.role === current && stage.status === "blocked" ? snapshot?.waiting_causes || [] : [];
        const label = causes.length === 1 ? causeLabels[causes[0]] || "Unavailable" : stageLabels[stage.status] || "Unknown";
        const Icon=stage.status === "done" ? CheckCircle2 : stage.status === "running" ? LoaderCircle : stage.status === "waiting" ? Circle : stage.status === "clarification" ? MessageCircle : stage.status === "error" ? AlertCircle : Clock3;
        return <li key={stage.role} data-stage={stage.role} data-stage-status={stage.status}>
          <Icon size={18} className={stage.status === "running" ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true" />
          <span className="investigation-role">{t(roleLabels[stage.role] || stage.role)}</span><span className="investigation-stage-state muted">{t(label)}</span>
          {causes.length > 1 && <ul className="investigation-stage-causes space-y-1 text-xs">{causes.map(cause=><li key={cause}>{t(causeLabels[cause] || "Unavailable")}</li>)}</ul>}
        </li>;
      })}</ol>
      {drafting && waiting && !!snapshot?.waiting_causes?.length && <ul className="text-xs muted">{snapshot.waiting_causes.filter(cause=>cause !== "unavailable").map(cause=><li key={cause}>{t(causeLabels[cause] || "Unavailable")}</li>)}</ul>}
    </div>
  </details>;
}
