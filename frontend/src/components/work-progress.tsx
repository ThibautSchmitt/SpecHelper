"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, ChevronDown, Circle, Clock3, LoaderCircle } from "lucide-react";
import { type WorkExecution, type WorkPhase } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { SafeMarkdown } from "@/components/safe-markdown";

const activities:Record<string,string>={preparing:"Preparing the request…",processing:"AI is processing…",search:"Searching project sources…",read:"Reading source files…",git:"Inspecting Git history…",command:"Using a tool…",tool:"Using a tool…",plan:"Updating the work plan…",reference:"Looking up references…",writing:"Writing the response…"};
const operations:Record<string,string>={search:"Search project sources",read:"Read source files",git:"Inspect Git history",command:"Use a tool",tool:"Use a tool",plan:"Update the work plan",reference:"Look up references"};
export function activityLabel(phases:WorkPhase[]) {
  const current=phases.filter(phase=>phase.active).at(-1);
  return current ? activities[current.activity] || "AI is processing…" : phases.length ? "AI is processing…" : "Preparing the request…";
}

export function ProgressDisclosure({label,subtitle,active,complete=false,attention=false,partial=false,className="",cycle,startedAt,unavailable=false,children}:{
  label:string;subtitle?:string;active:boolean;complete?:boolean;attention?:boolean;partial?:boolean;
  className?:string;cycle?:number|string;startedAt?:string|null;unavailable?:boolean;children:ReactNode;
}) {
  const {t}=useI18n();
  const [now,setNow]=useState(()=>Date.now());
  useEffect(()=>{if(!active)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[active]);
  const elapsed=startedAt ? Math.max(0,Math.floor((now-Date.parse(startedAt))/1000)) : null;
  const Icon=unavailable ? Clock3 : active ? LoaderCircle : complete ? CheckCircle2 : attention ? AlertCircle : Clock3;
  return <details className={`work-progress ${className}`} data-cycle={cycle}>
    <summary><Icon size={18} className={active&&!unavailable ? "investigation-active animate-spin motion-reduce:animate-none" : complete ? "work-complete" : attention ? "investigation-attention" : "muted"} aria-hidden="true"/>
      <span className="investigation-heading" role="status" aria-live="polite"><span>{t(unavailable ? "Progress updates unavailable" : label)}</span>{subtitle&&<span className="investigation-subtitle">{t(subtitle)}</span>}</span>
      {active&&elapsed!==null&&<span className="work-elapsed muted" aria-hidden="true">{Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,"0")}</span>}
      {partial&&<span className="badge">{t("Partial result")}</span>}<ChevronDown size={14} className="investigation-disclosure" aria-hidden="true"/>
    </summary>
    <div className="investigation-content space-y-3">{children}</div>
  </details>;
}

export function WorkSteps({phases,unavailable=false}:{phases:WorkPhase[];unavailable?:boolean}) {
  const {t}=useI18n();
  const events=phases.flatMap(phase=>phase.events.map(event=>({...event,key:`${phase.id}:${event.id}`,active:phase.active})));
  function list(items:typeof events) {return <ol className="work-observations" aria-label={t("Observed work")}>{items.map(event=>{
    const running=event.state==="running"&&event.active&&!unavailable;
    const Icon=event.state==="done" ? CheckCircle2 : event.state==="error" ? AlertCircle : running ? LoaderCircle : Circle;
    return <li key={event.key} data-work-state={event.state}><Icon size={14} className={running ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true"/><span>{t(operations[event.operation] || "Use a tool")}</span><span className="sr-only">{t(event.state==="done" ? "Completed" : event.state==="error" ? "Technical failure" : running ? "In progress" : "Stage completion not recorded")}</span></li>;
  })}</ol>;}
  return <>{events.length>4&&<details className="work-older"><summary>{t("Earlier work steps")}</summary>{list(events.slice(0,-4))}</details>}{list(events.slice(-4))}{!events.length&&<p className="text-xs muted">{t("No detailed work event has been reported.")}</p>}</>;
}

export function ResponsePreview({phases}:{phases:WorkPhase[]}) {
  const {t}=useI18n();
  const preview=phases.filter(phase=>phase.active).at(-1)?.preview;
  if(!preview)return null;
  return <div className="work-response-preview" aria-label={t("Draft response")}>
    <p className="text-xs muted mb-2">{t("Draft response · pending validation")}</p>
    <SafeMarkdown roleMentions>{preview}</SafeMarkdown>
  </div>;
}

export function DiscussionProgress({job,unavailable=false}:{job:WorkExecution;unavailable?:boolean}) {
  const waiting=job.status==="QUEUED"&&!!job.waiting_reason;
  const active=job.status==="RUNNING";
  const cause=job.waiting_causes?.[0];
  const label=job.status==="DONE" ? "Reply completed" : job.status==="ERROR" ? "Response interrupted" : job.status==="CANCELLED" ? "Response cancelled" : waiting ? cause==="quota" ? "Quota exhausted" : cause==="busy" ? "Assistant busy" : cause==="connection_missing" ? "No authenticated connection" : cause==="model_unavailable" ? "Model unavailable" : "Waiting for the selected AI connection." : active ? activityLabel(job.phases) : "I’m on it…";
  return <><ProgressDisclosure label={label} active={active} complete={job.status==="DONE"} attention={waiting||job.status==="ERROR"} className="discussion-progress" startedAt={job.started_at} unavailable={unavailable&&active}>
    <WorkSteps phases={job.phases} unavailable={unavailable&&active}/>
  </ProgressDisclosure><ResponsePreview phases={job.phases}/></>;
}
