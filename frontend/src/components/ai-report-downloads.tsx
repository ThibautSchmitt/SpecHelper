"use client";

import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { type RequestDetail, type ResultVersion } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { roleLabels } from "@/lib/orchestration";
import { SafeMarkdown } from "@/components/safe-markdown";

export function AIReportDownloads({value,result}:{value:RequestDetail;result:ResultVersion}) {
  const {t}=useI18n();
  const run=value.analysis_runs?.find(run=>run.number === result.run_number);
  const roles=["analyst","counter_analyst","verifier"].filter(role=>run?.role_reviews?.some(review=>review.public_role === role));
  if(!run || !roles.length || !["READY","PARTIAL"].includes(result.status))return null;
  function download(role:string) {
    const lines=[`# ${t(roleLabels[role])}`,"",value.title || value.need.split("\n")[0],"",`${t("Analysis")}: ${value.id}`,`${t("Version")}: ${result.number}`,`${t("Investigation progress")}: ${run!.number}`,`${t("Status")}: ${t(result.status === "READY" ? "Result available" : "Partial result")}`,"",t("A completed stage records execution, not a guarantee that its conclusions are correct."),""];
    const identities=[...new Set(run!.steps.filter(step=>step.public_role === role && step.status === "DONE").map(step=>[step.connection_name || step.provider || step.agent,step.model].filter(Boolean).join(" · ")).filter(Boolean))];
    lines.push(...identities.map(identity=>`- ${identity}`),"");
    for(const review of run!.role_reviews!.filter(review=>review.public_role === role)) {
      const labels:Record<string,string>={analyst:"Recorded findings",counter_independent:"Independent investigation",comparison:"Comparison of conclusions",focused_verification:"Focused verification",verifier:"Verification"};
      lines.push(`## ${t(labels[review.checkpoint] || "Recorded findings")}`,"",review.summary,"");
      for(const finding of review.findings){
        lines.push(`- ${finding.statement}${finding.status ? ` (${finding.status})` : ""}`);
        for(const source of finding.sources || [])lines.push("",...JSON.stringify(source,null,2).split("\n").map(line=>`    ${line}`),"");
      }
      for(const [label,items] of [["Agreements",review.agreements],["Review disagreements",review.issues],["Important limits and pending checks",review.limits]] as const){
        if(items.length)lines.push("",`### ${t(label)}`,"",...items.map(item=>`- ${item}`),"");
      }
    }
    const url=URL.createObjectURL(new Blob([lines.join("\n")],{type:"text/markdown;charset=utf-8"}));
    const anchor=document.createElement("a");anchor.href=url;anchor.download=`analysis-${value.id}-v${result.number}-${role}.md`;anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return <section aria-label={t("Individual AI reports")}>
    <h3 className="text-sm">{t("Individual AI reports")}</h3>
    <p className="mt-1 text-xs muted">{t("Optional downloads from recorded findings. These files are not attached to tickets.")}</p>
    <div className="mt-3 flex flex-wrap gap-2">{roles.map(role=><Button key={role} variant="outline" size="sm" onClick={()=>download(role)}><Download size={14} aria-hidden="true" />{t(roleLabels[role])} · .md</Button>)}</div>
    <details className="mt-3 text-sm"><summary className="cursor-pointer">{t("See the AI review")}</summary>
      <div className="mt-3 space-y-4">{roles.map(role=><section key={role}>
        <h4 className="mb-2"><span className="badge" data-role={role}>{t(roleLabels[role])}</span></h4>
        {run.role_reviews!.filter(review=>review.public_role===role).map(review=><div key={review.checkpoint} className="mb-3 space-y-2">
          {review.summary&&<SafeMarkdown>{review.summary}</SafeMarkdown>}
          {!!review.findings.length&&<ul className="list-disc pl-5">{review.findings.map((finding,index)=><li key={index}>{finding.statement}</li>)}</ul>}
          {[...review.issues,...review.limits].filter(item=>typeof item==="string").map((item,index)=><p key={index} className="text-xs muted">{item}</p>)}
        </div>)}
      </section>)}</div>
    </details>
  </section>;
}
