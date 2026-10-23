"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Markdown is untrusted data. Images cannot silently leak business content to remote hosts.
export function SafeMarkdown({ children }: { children: string }) {
  return <ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={{
    img: ({ alt }) => <span className="muted">{alt || "[image]"}</span>,
    a: ({ href, children }) => {
      const safe = href && (/^https?:\/\//i.test(href) || href.startsWith("/") && !href.startsWith("//") || href.startsWith("#"));
      return safe ? <a href={href} rel="noopener noreferrer" referrerPolicy="no-referrer">{children}</a> : <span>{children}</span>;
    },
  }}>{children}</ReactMarkdown>;
}
