"use client";

import { Children, isValidElement, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "@/components/code-block";
import { useI18n } from "@/lib/i18n";

export function markdownComponents(t: (key: string) => string): Components {
  return {
    table: ({ children }) => <div className="safe-markdown-table" role="region" aria-label={t("Data table")} tabIndex={0}><table>{children}</table></div>,
    pre: ({ children }) => {
      const code = Children.toArray(children)[0];
      if (isValidElement<{ children?: ReactNode; className?: string }>(code) && typeof code.props.children === "string") {
        const language = code.props.className?.match(/(?:^|\s)language-([^\s]+)/)?.[1] || "";
        return <CodeBlock code={code.props.children} language={language} />;
      }
      return <pre>{children}</pre>;
    },
    img: ({ alt }) => <span className="muted">{alt || t("Image")}</span>,
    a: ({ href, children }) => {
      const safe = href && (/^https?:\/\//i.test(href) || href.startsWith("/") && !href.startsWith("//") || href.startsWith("#"));
      return safe ? <a href={href} rel="noopener noreferrer" referrerPolicy="no-referrer">{children}</a> : <span>{children}</span>;
    },
  };
}

export function MarkdownReader({ children }: { children: string }) {
  const { t } = useI18n();
  return <div className="markdown-reader"><ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={markdownComponents(t)}>{children}</ReactMarkdown></div>;
}
