"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, ChevronDown, Circle, Clock3, LoaderCircle } from "lucide-react";
import { type AnalysisClock, type WorkExecution, type WorkPhase } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { executionSeconds } from "@/lib/execution-clock";
import { SafeMarkdown } from "@/components/safe-markdown";

const activities:Record<string,string>={preparing:"Preparing the request…",processing:"AI is processing…",search:"Searching project sources…",read:"Reading source files…",git:"Inspecting Git history…",command:"Running a command…",tool:"Operation in progress…",plan:"Updating the work plan…",reference:"Looking up references…",writing:"Writing the response…"};
const operations:Record<string,string>={search:"Search project sources",read:"Read source files",git:"Inspect Git history",command:"Run a command",plan:"Update the work plan",reference:"Look up references"};
export function activityLabel(phases:WorkPhase[]) {
  const current=phases.filter(phase=>phase.active).at(-1);
  return current ? activities[current.activity] || "AI is processing…" : phases.length ? "AI is processing…" : "Preparing the request…";
}

export function ProgressDisclosure({label,subtitle,active,complete=false,attention=false,partial=false,className="",cycle,startedAt,clock,unavailable=false,expandable=true,children}:{
  clock?:AnalysisClock;label:string;subtitle?:string;active:boolean;complete?:boolean;attention?:boolean;partial?:boolean;
  className?:string;cycle?:number|string;startedAt?:string|null;unavailable?:boolean;expandable?:boolean;children:ReactNode;
}) {
  const {t}=useI18n();
  const [now,setNow]=useState(()=>Date.now());
  useEffect(()=>{if(!active)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[active]);
  const elapsed=clock ? executionSeconds(clock,now,unavailable) : startedAt ? Math.max(0,Math.floor((now-Date.parse(startedAt))/1000)) : null;
  const Icon=unavailable ? Clock3 : active ? LoaderCircle : complete ? CheckCircle2 : attention ? AlertCircle : Clock3;
  const heading=<><Icon size={18} className={active&&!unavailable ? "investigation-active animate-spin motion-reduce:animate-none" : complete ? "work-complete" : attention ? "investigation-attention" : "muted"} aria-hidden="true"/>
      <span className="investigation-heading" role="status" aria-live="polite"><span>{t(unavailable ? "Progress updates unavailable" : label)}</span>{subtitle&&<span className="investigation-subtitle">{t(subtitle)}</span>}</span>
      {active&&elapsed!==null&&<span className="work-elapsed muted" aria-hidden="true">{Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,"0")}</span>}
      {partial&&<span className="badge">{t("Partial result")}</span>}</>;
  if(!expandable)return <div className={`work-progress ${className}`} data-cycle={cycle}><div className="work-progress-static">{heading}</div></div>;
  return <details className={`work-progress ${className}`} data-cycle={cycle}>
    <summary>{heading}<ChevronDown size={14} className="investigation-disclosure" aria-hidden="true"/></summary>
    <div className="investigation-content space-y-3">{children}</div>
  </details>;
}

export function WorkSteps({phases,unavailable=false}:{phases:WorkPhase[];unavailable?:boolean}) {
  const {t}=useI18n();
  const events=phases.flatMap(phase=>phase.events.map(event=>({...event,key:`${phase.id}:${event.id}`,active:phase.active})));
  if(!events.length)return null;
  const groups=phases.flatMap(phase=>{
    const rows:(typeof events[number]&{count:number})[]=[];
    for(const event of phase.events){
      const previous=rows.at(-1);
      if(previous&&event.state!=="running"&&previous.operation===event.operation&&previous.state===event.state){
        previous.count++;
      }else{
        rows.push({...event,key:`${phase.id}:${event.id}`,active:phase.active,count:1});
      }
    }
    return rows;
  });
  function list(items:typeof groups) {return <ol className="work-observations" aria-label={t("Observed work")}>{items.map(event=>{
    const running=event.state==="running"&&event.active&&!unavailable;
    const Icon=event.state==="done" ? CheckCircle2 : event.state==="error" ? AlertCircle : running ? LoaderCircle : Circle;
    const label=operations[event.operation] || (event.state==="done" ? "Operation completed" : event.state==="error" ? "Operation failed" : running ? "Operation in progress…" : "Assistant operation");
    return <li key={event.key} data-work-state={event.state}><Icon size={14} className={running ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true"/><span>{t(label)}</span>{event.count>1&&<span className="muted text-xs" aria-label={t("{count} operations",{count:event.count})}>× {event.count}</span>}<span className="sr-only">{t(event.state==="done" ? "Completed" : event.state==="error" ? "Technical failure" : running ? "In progress" : "Stage completion not recorded")}</span></li>;
  })}</ol>;}
  return <>{groups.length>4&&<details className="work-older"><summary>{t("Earlier work steps")}</summary>{list(groups.slice(0,-4))}</details>}{list(groups.slice(-4))}</>;
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
  const preparingAnalysis=job.operation==="analysis_preparation";
  const label=job.status==="DONE" ? "Reply completed" : job.status==="ERROR" ? preparingAnalysis ? "Analysis preparation interrupted" : "Response interrupted" : job.status==="CANCELLED" ? "Response cancelled" : waiting ? cause==="quota" ? "Quota limit reported" : cause==="busy" ? "Assistant busy" : cause==="connection_missing" ? "No authenticated connection" : cause==="model_unavailable" ? "Model unavailable" : "Waiting for the selected AI connection." : preparingAnalysis ? "Deep analysis in progress…" : active ? activityLabel(job.phases) : "I’m on it…";
  return <><ProgressDisclosure label={label} subtitle={preparingAnalysis&&!waiting?["QUEUED","RUNNING"].includes(job.status)?"Preparing analysis context…":undefined:undefined} active={active} complete={job.status==="DONE"} attention={waiting||job.status==="ERROR"} className="discussion-progress" startedAt={job.started_at} unavailable={unavailable&&active} expandable={job.phases.some(phase=>phase.events.length>0)}>
    <WorkSteps phases={job.phases} unavailable={unavailable&&active}/>
  </ProgressDisclosure>{!preparingAnalysis&&<ResponsePreview phases={job.phases}/>}</>;
}
