"use client";

import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";
import { ChevronDown, LoaderCircle, CheckCircle2, Clock3, CircleHelp, AlertCircle, Circle, MessageCircle } from "lucide-react";
import { SafeMarkdown } from "@/components/safe-markdown";
import { RoleMentions } from "@/components/role-mentions";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { type RequestDetail, type ResultVersion, type WorkExecution } from "@/lib/api";
import { activityLabel, DiscussionProgress, ProgressDisclosure, ResponsePreview, WorkSteps } from "@/components/work-progress";
import { useI18n } from "@/lib/i18n";
import { roleLabels } from "@/lib/orchestration";
import { conversationState } from "@/lib/conversation-state";
import type { SQLReceipt } from "@/lib/analysis-evidence";

type Run = NonNullable<RequestDetail["analysis_runs"]>[number];
const requestsSqlIds=(text:string)=>/\bquery[_ -]?(?:ids?|identifiers?)\b|\b(?:sql|receipt)\s+(?:ids?|identifiers?)\b|\b(?:ids?|identifiants?)\s+(?:techniques?\s+|internes?\s+)?(?:des?\s+|de la\s+|du\s+)?requ[eê]tes?\b|\bsql-[a-f\d]{32}-[a-f\d]{12}\b/i.test(text);

type Event = {
  id: string; at: string; speaker: "user" | "assistant"; content: string; label?: string;
  version?: number; child?: string; url?: string; sortAt?: number;
  run?: Run;
  markdown?: boolean;
  discussion?: boolean;
  work?: WorkExecution;
  sqlChecks?: SQLReceipt[];
  sourcesUrl?:string;
  compactSqlReferences?:boolean;
  subject?:string;
  ticketId?:string;
};

export function AnalysisConversation({ value, result, reply, actions, controls, resultActions, ticketActions, onSelectVersion, trackingUnavailable=false }: {
  value: RequestDetail; result?: ResultVersion | null; reply?: ReactNode;
  actions?: ReactNode; controls?: ReactNode; onSelectVersion?: (version: number) => void;
  trackingUnavailable?:boolean;
  resultActions?: (number:number)=>ReactNode;
  ticketActions?: (id:string)=>ReactNode;
}) {
  const { t, dateLocale } = useI18n();
  const runs = value.analysis_runs || [];
  const working = ["IN_PROGRESS", "WAITING_AI"].includes(conversationState(value));
  const pending = value.status === "NEEDS_CLARIFICATION";
  const messages = value.messages || [];
  const list=useRef<HTMLOListElement>(null);
  const nearBottom=useRef(true);
  useEffect(()=>{
    const root=list.current?.closest<HTMLElement>(".dashboard-center") || document.scrollingElement;
    if(!root)return;
    nearBottom.current=true;
    function measure(){if(root)nearBottom.current=root.scrollHeight-root.clientHeight-root.scrollTop<160;}
    function disclosure(event:PointerEvent){if((event.target as Element)?.closest("summary"))nearBottom.current=false;}
    const observer=new ResizeObserver(()=>{if(nearBottom.current)root!.scrollTo({top:root!.scrollHeight,behavior:"instant"});});
    if(list.current)observer.observe(list.current);
    root.addEventListener("scroll",measure,{passive:true});list.current?.addEventListener("pointerdown",disclosure);
    const node=list.current;return()=>{observer.disconnect();root.removeEventListener("scroll",measure);node?.removeEventListener("pointerdown",disclosure);};
  },[value.id]);
  const lastClarification = messages.filter(message => ["questions", "clarification"].includes(message.kind)).at(-1);
  const pendingMessage = pending && lastClarification?.content === value.questions.map(question=>question.question).join("\n") ? lastClarification : undefined;
  let latestUserText=value.need;
  const events: Event[] = messages.filter(message => {
    if (["result", "decision_revision", "error"].includes(message.kind)) return false;
    if(message.role === "assistant" && message.kind === "ticket_preparation" && message.data?.conversation_ticket_id)return false;
    // Pending questions appear once, together with their real answer controls.
    return message.id !== pendingMessage?.id;
  }).map(message => {
    const answers = message.data?.answers;
    if(message.role==='user')latestUserText=message.content;
    const stale=message.role === "assistant" && message.kind === "discussion_reply" && message.data?.response_status === "stale";
    const observations=message.data?.observations as {database_checks?:SQLReceipt[];web_checks?:unknown[];context_usage?:unknown[]}|undefined;
    const checks=Array.isArray(observations?.database_checks)?observations.database_checks.filter(check=>check&&typeof check.query_id==="string"&&typeof check.sql==="string"):[];
    return { id: `message-${message.id}`, at: message.created_at,
      speaker: message.role === "user" ? "user" : "assistant",
      content: stale ? "" : answers && typeof answers === "object" ? Object.values(answers).filter(item => typeof item === "string").join("\n\n") : message.content,
      label: stale ? "Response interrupted" : message.kind === "need_revision" ? "Need updated" : undefined,
      markdown: message.kind === "discussion_reply",
      sqlChecks: checks,
      compactSqlReferences:!requestsSqlIds(latestUserText),
      sourcesUrl:message.role==='assistant'&&(checks.length||observations?.web_checks?.length||observations?.context_usage?.length||/`[^`\n]+\.(?:py|tsx?|jsx?|java|go|rs|md|pdf|docx|txt|ya?ml|xml|json)(?::\d+(?:[-–]\d+)?)?`/i.test(message.content))?`/analyses/${value.id}/messages/${message.id}/sources`:undefined,
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
      content: typeof summary === "string" ? summary : "", sqlChecks: displayed?.evidence?.database?.checks,
      compactSqlReferences:!requestsSqlIds(value.need),
      sourcesUrl:displayed?.evidence?.claims?.some(claim=>claim.sources?.length)||displayed?.evidence?.database?.checks?.length||displayed?.context_usage?.some(usage=>usage.status==='observed')?`/analyses/${value.id}/versions/${version.number}/sources`:undefined,
      subject:version.subject,
      label: version.status === "ERROR" ? "Deep analysis interrupted" : version.status === "PARTIAL" || displayed?.evidence?.blocking ? "Deep analysis finished with limits" : "Deep analysis completed" });
  }
  for(const ticket of value.conversation_tickets || [])events.push({id:`ticket-${ticket.id}`,at:ticket.created_at,speaker:"assistant",content:ticket.title,ticketId:ticket.id,label:ticket.status === "PUBLISHED" ? "Ticket published" : ticket.status === "ERROR" ? "Ticket publication failed" : "Ticket in preparation"});
  for (const publication of value.publications || []) events.push({ id:`publication-${publication.id}`, at:publication.created_at, speaker:"assistant", content:publication.title,
    label:publication.status === "PUBLISHED" ? "Ticket published" : publication.status === "ERROR" ? "Ticket publication failed" : "Ticket publication not confirmed",
    url:publication.status === "PUBLISHED" && /^https?:\/\//i.test(publication.url) ? publication.url : undefined });
  for (const run of runs) {
    const at=run.started_at || run.steps.find(step=>step.started_at)?.started_at || value.created_at;
    const start=new Date(at).getTime();
    const terminal=["READY","PARTIAL","ERROR","CANCELLED"].includes(run.execution?.status || run.status);
    const active=!terminal && run.number === Math.max(...runs.map(run=>run.number)) && value.discussion?.mode !== "discussion" && (working || pending);
    const work=value.work_progress?.find(job=>job.kind==="analysis"&&job.run_number===run.number);
    // Older failed cycles sometimes have no finished_at. Their recorded steps
    // still bound the cycle; later discussion messages must never move it.
    const recordedEnd=Math.max(start,...[
      run.finished_at,work?.finished_at,
      ...run.steps.flatMap(step=>[step.started_at,step.finished_at]),
    ].filter((stamp):stamp is string=>!!stamp).map(stamp=>Date.parse(stamp)).filter(Number.isFinite));
    const end=active ? Infinity : recordedEnd;
    const latestInput=Math.max(start,...events.filter(event=>event.speaker === "user").map(event=>new Date(event.at).getTime()).filter(time=>time >= start && time <= end));
    // Only the active cycle follows resumed input. Closed cycles stay in history.
    events.push({id:`progress-${run.number}`,at,sortAt:latestInput + 1,speaker:"assistant",content:"",run});
  }
  if (!runs.length && (working || pending) && value.discussion?.mode !== "discussion") events.push({id:"progress-pending",at:value.created_at,sortAt:Math.max(new Date(value.created_at).getTime(),...events.filter(event=>event.speaker === "user").map(event=>new Date(event.at).getTime()))+1,speaker:"assistant",content:"",run:{number:0,status:value.status,steps:[]}});
  for(const job of value.work_progress?.filter(job=>job.kind==="discussion") || [])events.push({id:`discussion-progress-job-${job.id}`,at:job.created_at,speaker:"assistant",content:"",work:job});
  if (!value.work_progress?.some(job=>job.kind==="discussion") && value.discussion?.mode === "discussion" && value.discussion.job && ["QUEUED","RUNNING"].includes(value.discussion.job.status)) events.push({
    id:`discussion-progress-${value.discussion.revision}`,at:value.discussion.job.created_at,speaker:"assistant",content:"",discussion:true,
    work:{...value.discussion.job,kind:"discussion",waiting_causes:[],phases:[]},
  });
  events.sort((left, right) => (left.sortAt ?? new Date(left.at).getTime()) - (right.sortAt ?? new Date(right.at).getTime()));
  const lastMessageAt = [
    ...events.filter(event => !event.run && !event.work && !event.discussion).map(event => event.at),
    ...(pendingMessage ? [pendingMessage.created_at] : []),
  ].reduce((latest, at) => Date.parse(at) > Date.parse(latest) ? at : latest, value.created_at);

  return <Card className="analysis-conversation" aria-label={t("Conversation")}>
    <div className="conversation-toolbar">
      <dl className="conversation-metadata">
        <div><dt>{t("Request date:")}</dt><dd><time dateTime={value.created_at}>{new Date(value.created_at).toLocaleString(dateLocale)}</time></dd></div>
        <div><dt>{t("Last message:")}</dt><dd><time dateTime={lastMessageAt}>{new Date(lastMessageAt).toLocaleString(dateLocale)}</time></dd></div>
      </dl>
    </div>
    <ol className="conversation-messages" ref={list}>
      {events.map(event => <li key={event.id} className={`conversation-message conversation-${event.speaker}`} data-message={event.id}>
        <article className="conversation-bubble">
          {event.run && <InvestigationProgress run={event.run} work={value.work_progress?.find(job=>job.kind==="analysis"&&job.run_number===event.run!.number)} unavailable={trackingUnavailable}/>}
          {event.work&&<DiscussionProgress job={event.work} unavailable={trackingUnavailable}/>}
          {event.label && <p className="mb-2 flex items-center gap-2 text-xs font-medium text-primary">{event.discussion && <LoaderCircle size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true"/>}{t(event.label)}{event.version ? ` · v${event.version}` : ""}</p>}
          {event.subject && <p className="mb-2 text-xs muted">{t("Subject")}: {event.subject}</p>}
          {event.content && (event.version || event.markdown ? <div className="conversation-answer break-words text-sm leading-7"><SafeMarkdown roleMentions compactSqlReferences={event.compactSqlReferences!==false} sqlChecks={event.sqlChecks} sourcesUrl={event.sourcesUrl}>{event.content}</SafeMarkdown></div> : <p className="conversation-message-text whitespace-pre-wrap break-words text-sm leading-7">{event.speaker === "assistant" ? <RoleMentions>{event.content}</RoleMentions> : event.content}</p>)}
          {event.child && <Link className="mt-3 inline-block text-sm text-primary underline" href={`/analyses/${event.child}`}>{t("Open linked change")}</Link>}
          {event.url && <a className="mt-3 inline-block text-sm text-primary underline" href={event.url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{t("Open published ticket")}</a>}
          {event.version && event.version !== result?.number && <Button variant="ghost" size="sm" className="mt-3" onClick={()=>onSelectVersion?.(event.version!)}>{t("Read result version {number}", {number:event.version})}</Button>}
          {event.version && <div className="mt-3 flex flex-wrap gap-2">{resultActions?.(event.version)}</div>}
          {event.ticketId && <div className="mt-3 flex flex-wrap gap-2">{ticketActions?.(event.ticketId)}</div>}
          {event.version === result?.number && result && <>
            {value.conclusions_stale && <p className="mt-3 text-sm font-medium">{t("Previous conclusions need reassessment")}</p>}
            {(result.status !== "READY" || result.evidence?.blocking) && <p className="mt-3 text-sm muted">{t("Some conclusions remain unverified. See the analysis report for the limits and evidence.")}</p>}
            {value.discussion?.enabled && result.evidence?.blocking && !!result.evidence.limitations?.length && <ul className="mt-2 list-disc pl-5 text-sm muted">{[...new Set(result.evidence.limitations)].slice(0,3).map(limit=><li key={limit}>{limit}</li>)}</ul>}
            <div className="mt-5 flex flex-wrap gap-2">{actions}</div>
          </>}
        </article>
      </li>)}
    </ol>
    <div className="conversation-reply" id={pending || value.conversation_state === "AWAITING_REPLY" ? "conversation-clarification" : undefined}>
      <div className="conversation-reply-content">{reply}</div>
    </div>
    {controls && <div className="flex flex-wrap gap-2">{controls}</div>}
  </Card>;
}

export function conversationAnswer(result:ResultVersion) {
  // Display the accepted synthesis, never a concatenation of preliminary agent reports.
  const summary=result.explanation?.response || result.explanation?.summary || result.ticket?.proposed_solution || result.ticket?.context;
  if (typeof summary === "string" && summary.trim()) return summary.trim();
  const explanation = result.explanation?.business_explanation;
  return typeof explanation === "string" ? explanation.trim() : "";
}

const stageLabels:Record<string,string>={done:"Completed",running:"In progress",waiting:"Upcoming",not_started:"Not started",blocked:"AI unavailable",clarification:"Clarification requested",error:"Technical failure",cancelled:"Analysis cancelled",unknown:"Stage completion not recorded"};
const causeLabels:Record<string,string>={quota:"Quota limit reported",busy:"Assistant busy",connection_missing:"No authenticated connection",model_unavailable:"Model unavailable",unavailable:"Unavailable"};

function InvestigationProgress({run,work,unavailable=false}:{run:Run;work?:WorkExecution;unavailable?:boolean}) {
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
  const headline=status === "NEEDS_CLARIFICATION" ? "Needs clarification" : status === "ERROR" ? "Analysis interrupted" : status === "CANCELLED" ? "Analysis cancelled" : terminal ? allDone ? "Investigation finished" : "Investigation finished · verification incomplete" : status === "QUEUED" ? snapshot?.waiting_reason ? "Waiting for an AI resource" : "In queue" : current === "counter_analyst" ? "Counter-analysis in progress…" : current === "verifier" ? "Verification in progress…" : "Analysis in progress";
  const observed=work?.phases || [];
  return <><ProgressDisclosure className="investigation-progress" cycle={run.number || "pending"} active={active} complete={terminal&&allDone} attention={waiting||clarification||status==="ERROR"} partial={status==="PARTIAL"} subtitle={subtitle} startedAt={work?.started_at} unavailable={unavailable&&active}
    label={drafting&&waiting ? "Final response awaiting an assistant" : drafting&&active ? "Preparing final response…" : active&&observed.some(phase=>phase.active) ? activityLabel(observed) : active ? "Analysis in progress" : waiting ? "Waiting for an available assistant" : headline}>
      <ol className="investigation-stages" aria-label={t("Investigation stages")}>{stages.map(stage=>{
        const causes = !drafting && stage.role === current && stage.status === "blocked" ? snapshot?.waiting_causes || [] : [];
        const label = causes.length === 1 ? causeLabels[causes[0]] || "Unavailable" : stageLabels[stage.status] || "Unknown";
        const Icon=stage.status === "done" ? CheckCircle2 : stage.status === "running" ? LoaderCircle : ["waiting","not_started"].includes(stage.status) ? Circle : stage.status === "clarification" ? MessageCircle : stage.status === "error" ? AlertCircle : Clock3;
        return <li key={stage.role} data-stage={stage.role} data-stage-status={stage.status}>
          <Icon size={18} className={stage.status === "running" && !unavailable ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true" />
          <span className="investigation-role"><span className="badge connection-tag connection-role-tag" data-role={stage.role}>{t(roleLabels[stage.role] || stage.role)}</span></span><span className="investigation-stage-state muted">{t(label)}</span>
          {causes.length > 1 && <ul className="investigation-stage-causes space-y-1 text-xs">{causes.map(cause=><li key={cause}>{t(causeLabels[cause] || "Unavailable")}</li>)}</ul>}
          {!!observed.filter(phase=>phase.role===stage.role).length&&<details className="work-role-steps"><summary>{t("Work steps")}</summary><WorkSteps phases={observed.filter(phase=>phase.role===stage.role)} unavailable={unavailable}/></details>}
        </li>;
      })}</ol>
      {drafting && waiting && !!snapshot?.waiting_causes?.length && <ul className="text-xs muted">{snapshot.waiting_causes.filter(cause=>cause !== "unavailable").map(cause=><li key={cause}>{t(causeLabels[cause] || "Unavailable")}</li>)}</ul>}
  </ProgressDisclosure><ResponsePreview phases={observed}/></>;
}
