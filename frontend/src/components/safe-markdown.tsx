"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Children, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import {ChevronDown} from "lucide-react";
import { RoleMentions } from "@/components/role-mentions";
import { useI18n } from "@/lib/i18n";
import type { SQLReceipt } from "@/lib/analysis-evidence";
import { SourceDetails } from "@/components/source-details";
import { markdownComponents } from "@/components/markdown-reader";

function sqlReferences(markdown:string){
  let fence="",length=0;
  const prose=markdown.split("\n").filter(line=>{
    const match=line.match(/^ {0,3}(`{3,}|~{3,})/);
    if(fence){if(match&&match[1][0]===fence&&match[1].length>=length){fence="";}return false;}
    if(match){fence=match[1][0];length=match[1].length;return false;}
    return !/^(?: {4}|\t)/.test(line);
  }).join("\n").replace(/`([^`\n]+)`/g,(_,code:string)=>/^sql-[a-f\d]{32}-[a-f\d]{12}$/i.test(code)?code:"");
  return [...new Set(prose.match(/\bsql-[a-f\d]{32}-[a-f\d]{12}\b/gi)||[])];
}

// Markdown is untrusted data. Images cannot silently leak business content to remote hosts.
export function SafeMarkdown({ children, roleMentions=false, compactSqlReferences=false, sqlChecks=[],sourcesUrl }: { children: string; roleMentions?:boolean; compactSqlReferences?:boolean; sqlChecks?:SQLReceipt[];sourcesUrl?:string }) {
  const {t}=useI18n();
  const prefix=useId();
  const focus=useRef("");
  const [selected,setSelected]=useState<string[]>([]);
  useLayoutEffect(()=>{if(focus.current&&document.activeElement===document.body)document.getElementById(focus.current)?.focus({preventScroll:true});},[selected]);
  const references=sqlReferences(children);
  const reference=(raw:string,id:string)=><button key={id} id={id} type="button" className="sql-reference-link" aria-expanded={selected.includes(raw)} onClick={()=>{focus.current=id;setSelected(current=>current.includes(raw)?current.filter(id=>id!==raw):[...current,raw]);}}>{t("SQL check {number}",{number:references.indexOf(raw)+1})}<ChevronDown size={12} aria-hidden="true"/></button>;
  const text=(children:ReactNode,offset=0)=>Children.map(children,(child,part)=>typeof child === "string" ? child.split(/(sql-[a-f\d]{32}-[a-f\d]{12})/gi).map((piece,index)=>compactSqlReferences&&references.includes(piece)?reference(piece,`${prefix}-text-${offset}-${part}-${index}`):roleMentions?<RoleMentions key={index}>{piece}</RoleMentions>:piece) : child);
  return <><ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={{
    ...markdownComponents(t),
    code: ({children,node,className,...props})=>{
      const raw=String(children).trim();
      const index=references.indexOf(raw);
      // A fenced code example must keep its exact contents, including literal IDs.
      const inline=!!node?.position&&node.position.start.line===node.position.end.line;
      const id=`${prefix}-sql-${index}-${node?.position?.start.offset}`;
      return compactSqlReferences&&inline&&index>=0 ? reference(raw,id) : <code className={className} {...props}>{children}</code>;
    },
    ...(roleMentions||compactSqlReferences ? {
      p: ({children,node})=><p>{text(children,node?.position?.start.offset)}</p>,
      li: ({children,node})=><li>{text(children,node?.position?.start.offset)}</li>,
      strong: ({children,node})=><strong>{text(children,node?.position?.start.offset)}</strong>,
      em: ({children,node})=><em>{text(children,node?.position?.start.offset)}</em>,
    } : {}),
  }}>{children}</ReactMarkdown>
  {(sourcesUrl||compactSqlReferences&&(references.length>0||sqlChecks.length>0))&&<SourceDetails url={sourcesUrl} checks={sqlChecks} referenceIds={references} selected={selected} onSelect={setSelected}/>}
  </>;
}
