"use client";

import { useMemo, type ReactNode } from "react";
import { common, createLowlight } from "lowlight";
import type { RootContent } from "hast";
import { useI18n } from "@/lib/i18n";

const highlighter = createLowlight(common);

const extensions: Record<string, string> = {
  py: "python", js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript",
  ts: "typescript", tsx: "typescript", sql: "sql", pgsql: "sql", cs: "csharp",
  rb: "ruby", rs: "rust", sh: "bash", zsh: "bash", yml: "yaml", toml: "ini",
  html: "xml", htm: "xml", vue: "xml", svelte: "xml", svg: "xml", md: "markdown",
  h: "c", hpp: "cpp", cc: "cpp", patch: "diff", kt: "kotlin", pl: "perl",
};

export function sourceLanguage(filename = "") {
  const name = filename.split(/[\\/]/).pop()?.toLowerCase() || "";
  const extension = name.includes(".") ? name.split(".").pop()! : name;
  const language = extensions[extension] || extension;
  return highlighter.registered(language) ? language : "";
}

function renderTokens(nodes: RootContent[]): ReactNode {
  return nodes.map((node, index) => {
    if (node.type === "text") return node.value;
    if (node.type !== "element") return null;
    // Only classes and text from the highlighter's AST reach React. Source HTML
    // is never inserted into the DOM, and no source-defined element is created.
    const classes = node.properties.className;
    return <span key={index} className={Array.isArray(classes) ? classes.join(" ") : undefined}>{renderTokens(node.children)}</span>;
  });
}

export function CodeBlock({ code, language = "" }: { code: string; language?: string }) {
  const { t } = useI18n();
  const normalized = language.toLowerCase();
  const tokens = useMemo(() => {
    if (!normalized || !highlighter.registered(normalized) || code.length > 100000) return code;
    try { return renderTokens(highlighter.highlight(normalized, code).children); }
    catch { return code; }
  }, [code, normalized]);
  return <div className="code-reader">
    <div className="code-reader-heading">{normalized || t("Plain text")}</div>
    <pre tabIndex={0} aria-label={t("Code excerpt")}><code className={normalized ? `language-${normalized}` : undefined}>{tokens}</code></pre>
  </div>;
}
