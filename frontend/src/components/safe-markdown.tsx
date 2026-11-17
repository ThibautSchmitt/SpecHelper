"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Root, Paragraph, PhrasingContent, BlockContent, Content } from "mdast";
import { Children, createContext, useContext, useId, useLayoutEffect, useRef, useState, type ComponentProps, type ReactNode } from "react";
import {ChevronDown} from "lucide-react";
import { RoleMentions } from "@/components/role-mentions";
import { useI18n } from "@/lib/i18n";
import type { SQLReceipt } from "@/lib/analysis-evidence";
import { SourceDetails } from "@/components/source-details";
import { markdownComponents } from "@/components/markdown-reader";

const SourceContext=createContext<ComponentProps<typeof SourceDetails>|null>(null);
function MarkdownSourceDetails({className,children}:{className?:string;children?:ReactNode}){
  const props=useContext(SourceContext);
  return className==="source-details-slot"&&props?<SourceDetails {...props}>{children}</SourceDetails>:<div className={className}>{children}</div>;
}

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
  // Fold explicitly labelled evidence, without guessing which ordinary business
  // statements or code examples should disappear from the answer.
  function sourceNotes(){
    return (tree:Root)=>{
      if(!roleMentions&&!compactSqlReferences&&!sourcesUrl)return;
      const notes:BlockContent[]=[];
      const plain=(nodes:PhrasingContent[]):string=>nodes.map(node=>"value" in node?node.value:"children" in node?plain(node.children):"").join("");
      const isReference=(node:PhrasingContent)=>node.type==="link"||node.type==="inlineCode"&&(/[/\\]|\.[a-z0-9]{1,8}(?::\d+)?$/i.test(node.value)||/^[a-f\d]{7,40}$/i.test(node.value));
      const hasReference=(node:Content):boolean=>node.type==="inlineCode"||node.type==="link"?isReference(node):"children" in node&&node.children.some(hasReference);
      const labelled=(label:string)=>/^(?:sources?(?: (?:et|and|&) (?:verifications?|checks?))?|sources? (?:consultees?|consulted)|references(?: techniques?)?|elements? verifies?|verified (?:elements?|findings|evidence)|verifications?(?: effectuees?| realisees?| details)?|checks? performed)(?=$|\s*[:：]|\s+(?:dans|in|a|at|on)\b)/i.test(label.normalize("NFD").replace(/\p{M}/gu,"").trim());
      let skipUntil=0;
      tree.children=tree.children.flatMap<Root["children"][number]>((node,index,nodes)=>{
        if(index<skipUntil)return [];
        if(node.type==="heading"&&labelled(plain(node.children))){
          let end=index+1;
          let found=hasReference(node);
          while(end<nodes.length){
            const next=nodes[end];
            if(next.type==="heading"&&next.depth<=node.depth)break;
            if(found&&next.type==="paragraph"&&!hasReference(next))break;
            found=found||hasReference(next);end++;
          }
          const section=nodes.slice(index,end);
          if(!section.some(hasReference))return [node];
          // The disclosure already supplies the generic source-section title.
          notes.push(...section.slice(hasReference(node)?0:1).filter((part):part is BlockContent=>part.type!=="definition"));
          skipUntil=end;return [];
        }
        if(node.type!=="paragraph")return [node];
        const label=plain(node.children).trim();
        const last=node.children.findLastIndex(isReference);
        const next=nodes[index+1];
        const sourceList=next?.type==="list"&&hasReference(next)?next:null;
        if(!labelled(label)||(last<0&&!sourceList))return [node];
        const archive=(paragraph:Paragraph)=>{
          notes.push(paragraph);
          if(sourceList){notes.push(sourceList);skipUntil=index+2;}
        };
        // Keep any following sentence (including verification limits) in the
        // answer, even when the model put it in the bibliography paragraph.
        for(let index=last+1;index<node.children.length;index++){
          const child=node.children[index];
          if(child.type!=="text")continue;
          const boundary=child.value.match(/[.!?]\s+(?=\p{Lu})/u);
          if(!boundary)continue;
          const end=boundary.index!+boundary[0].length;
          archive({...node,children:[...node.children.slice(0,index),{...child,value:child.value.slice(0,end).trimEnd()}]});
          return [{...node,children:[{...child,value:child.value.slice(end)},...node.children.slice(index+1)]}];
        }
        archive(node);return [];
      });
      if(sourcesUrl||notes.length||compactSqlReferences&&(references.length||sqlChecks.length))tree.children.push({
        type:"blockquote",children:notes,
        data:{hName:"div",hProperties:{className:["source-details-slot"]}},
      });
    };
  }
  const reference=(raw:string,id:string)=><button key={id} id={id} type="button" className="sql-reference-link" aria-expanded={selected.includes(raw)} onClick={()=>{focus.current=id;setSelected(current=>current.includes(raw)?current.filter(id=>id!==raw):[...current,raw]);}}>{t("SQL check {number}",{number:references.indexOf(raw)+1})}<ChevronDown size={12} aria-hidden="true"/></button>;
  const text=(children:ReactNode,offset=0)=>Children.map(children,(child,part)=>typeof child === "string" ? child.split(/(sql-[a-f\d]{32}-[a-f\d]{12})/gi).map((piece,index)=>compactSqlReferences&&references.includes(piece)?reference(piece,`${prefix}-text-${offset}-${part}-${index}`):roleMentions?<RoleMentions key={index}>{piece}</RoleMentions>:piece) : child);
  return <SourceContext.Provider value={{url:sourcesUrl,checks:sqlChecks,referenceIds:references,selected,onSelect:setSelected}}><ReactMarkdown skipHtml remarkPlugins={[remarkGfm,sourceNotes]} components={{
    ...markdownComponents(t),
    div:MarkdownSourceDetails,
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
  }}>{children}</ReactMarkdown></SourceContext.Provider>;
}
