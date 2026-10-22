"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Download, FileText, Plus } from "lucide-react";
import { AnalysisContext } from "@/components/analysis-context";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, send, type QuestionDocument, type RequestDetail, type ResultVersion } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function QuestionResult({ questionId, result, versions, latestNumber, selectedNumber, onSelect }: {
  questionId: string; result: ResultVersion; versions: RequestDetail["versions"];
  latestNumber?: number; selectedNumber: number | null; onSelect: (number: number | null) => void;
}) {
  const { t, dateLocale } = useI18n();
  const [copied, setCopied] = useState(false);
  const [kind, setKind] = useState<QuestionDocument["kind"]>("mixed");
  const [documents, setDocuments] = useState<QuestionDocument[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const markdown = result.answer_markdown || result.markdown;
  const base = `/questions/${questionId}/versions/${result.number}`;
  useEffect(() => {
    let alive = true;
    setDocuments([]);
    setCopied(false);
    setError("");
    api<QuestionDocument[]>(`${base}/documents`).then(value => { if (alive) setDocuments(value); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [base]);
  async function copy() {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError(t("Copying is unavailable in this browser. Download the Markdown instead."));
    }
  }
  async function generate(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const document = await send<QuestionDocument>(`${base}/documents`, { kind });
      setDocuments(value => [document, ...value.filter(item => item.id !== document.id)]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const labels = { business: "Business documentation", technical: "Technical documentation", mixed: "Mixed documentation" };
  return <>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2>{t("Explanation")}</h2>
        <label className="sr-only" htmlFor="result-version">{t("Result version")}</label>
        <select id="result-version" value={selectedNumber ?? "latest"} onChange={e => onSelect(e.target.value === "latest" ? null : Number(e.target.value))}>
          <option value="latest">{t("Current version · v")}{latestNumber}</option>
          {versions.filter(version => version.number !== latestNumber || version.number === selectedNumber).map(version => <option key={version.number} value={version.number}>{t("Version")} {version.number} · {new Date(version.created_at).toLocaleString(dateLocale)}</option>)}
        </select>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={copy}><Copy size={16} />{copied ? t("Copied!") : t("Copy explanation")}</Button>
        <Button variant="outline" asChild><a href={result.artifacts["answer.md"] || `/api${base}/artifacts/answer.md`}><Download size={16} />{t("Download explanation")}</a></Button>
        <Button asChild><Link href={`/?from_question=${questionId}&version=${result.number}`}><Plus size={16} />{t("Create a request")}</Link></Button>
      </div>
    </div>
    <Card>
      <AnalysisContext workflow="question" requestId={questionId} runNumber={result.run_number} snapshot={result.context_snapshot} usage={result.context_usage} />
      <div className="question-markdown mt-5 break-words" data-testid="question-explanation"><ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown></div>
    </Card>
    <Card>
      <h2 className="flex items-center gap-2"><FileText size={19} />{t("Create documentation")}</h2>
      <p className="mt-2 text-sm muted">{t("Create a Markdown document from the displayed answer. It stays linked to this answer version and its Git references.")}</p>
      {error && <p role="alert" className="mt-3 text-sm text-red-800">{t(error)}</p>}
      <form onSubmit={generate} className="mt-4 flex flex-wrap items-end gap-3">
        <div><label className="mb-2 block text-sm" htmlFor="documentation-kind">{t("Documentation format")}</label><select id="documentation-kind" value={kind} disabled={busy} onChange={e => setKind(e.target.value as QuestionDocument["kind"])}>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{t(label)}</option>)}</select></div>
        <Button disabled={busy}>{busy ? t("Preparing documentation…") : t("Generate documentation")}</Button>
      </form>
      {!!documents.length && <ul className="mt-5 space-y-3">{documents.map(document => <li key={document.id} className="rounded-lg border p-3">
        <p className="text-sm font-medium">{t(labels[document.kind])} · {t("Source answer version {number}", { number: document.source_version })}</p>
        <p className="mt-1 text-xs muted">{new Date(document.created_at).toLocaleString(dateLocale)} · {document.language.toUpperCase()}</p>
        <a className="mt-2 inline-flex items-center gap-2 text-sm text-primary underline" href={document.download_url}><Download size={14} />{t("Download documentation")}</a>
        <details className="mt-2 text-sm"><summary className="cursor-pointer">{t("Preview documentation")}</summary><div className="question-markdown mt-3 break-words"><ReactMarkdown remarkPlugins={[remarkGfm]}>{document.markdown}</ReactMarkdown></div></details>
      </li>)}</ul>}
    </Card>
  </>;
}
