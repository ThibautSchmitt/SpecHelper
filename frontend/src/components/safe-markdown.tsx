"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Children, type ReactNode } from "react";
import { RoleMentions } from "@/components/role-mentions";

// Markdown is untrusted data. Images cannot silently leak business content to remote hosts.
export function SafeMarkdown({ children, roleMentions=false }: { children: string; roleMentions?:boolean }) {
  const text=(children:ReactNode)=>Children.map(children,child=>typeof child === "string" ? <RoleMentions>{child}</RoleMentions> : child);
  return <ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={{
    ...(roleMentions ? {
      p: ({children}:{children?:ReactNode})=><p>{text(children)}</p>,
      li: ({children}:{children?:ReactNode})=><li>{text(children)}</li>,
      strong: ({children}:{children?:ReactNode})=><strong>{text(children)}</strong>,
      em: ({children}:{children?:ReactNode})=><em>{text(children)}</em>,
    } : {}),
    img: ({ alt }) => <span className="muted">{alt || "[image]"}</span>,
    a: ({ href, children }) => {
      const safe = href && (/^https?:\/\//i.test(href) || href.startsWith("/") && !href.startsWith("//") || href.startsWith("#"));
      return safe ? <a href={href} rel="noopener noreferrer" referrerPolicy="no-referrer">{children}</a> : <span>{children}</span>;
    },
  }}>{children}</ReactMarkdown>;
}
