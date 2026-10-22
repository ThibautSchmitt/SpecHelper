"use client";
import { useI18n } from "@/lib/i18n";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Paperclip, Plus, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  send,
  statuses,
  type Environment,
  type RequestItem,
  type QuestionTransfer,
} from "@/lib/api";

export function WorkItemForm({ workflow = "request" }: { workflow?: "request" | "question" }) {
  const isQuestion = workflow === "question";
  const base = isQuestion ? "/questions" : "/requests";
  const search = useSearchParams();
  const sourceQuestion = !isQuestion ? search.get("from_question") : null;
  const sourceVersion = Number(search.get("version"));
  const [transfer, setTransfer] = useState<QuestionTransfer | null>(null);
  const [includeContext, setIncludeContext] = useState(true);
  const { t, dateLocale } = useI18n();
  const router = useRouter();
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [environment, setEnvironment] = useState("");
  const [need, setNeed] = useState("");
  const [confrontation, setConfrontation] = useState(false);
  const [allowConfrontation, setAllowConfrontation] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ allow_confrontation: boolean }>("/settings")
      .then((v) => setAllowConfrontation(v.allow_confrontation !== false))
      .catch(() => {});
    Promise.all([
      api<Environment[]>("/environments"),
      api<RequestItem[]>(base),
    ])
      .then(([e, r]) => {
        setEnvironments(e);
        setRequests(r);
      })
      .catch((e) => setError(e.message));
  }, [base]);
  useEffect(() => {
    if (!sourceQuestion) { setTransfer(null); return; }
    let alive = true;
    setTransfer(null);
    setIncludeContext(true);
    if (!Number.isInteger(sourceVersion) || sourceVersion < 1) {
      setError(t("Choose a valid source answer version."));
      return;
    }
    api<QuestionTransfer>(`/questions/${sourceQuestion}/versions/${sourceVersion}/transfer`)
      .then(value => { if (alive) { setTransfer(value); setEnvironment(String(value.environment_id || "")); } })
      .catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [sourceQuestion, sourceVersion]);
  async function analyze(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const contextFileCount = sourceQuestion && includeContext ? 1 : 0;
      if (files.length + contextFileCount > 20)
        throw new Error(t("A maximum of 20 attachments is allowed.") + (contextFileCount ? " " + t("The question context counts as one attachment.") : ""));
      if (files.some((file) => file.size > 25 * 1024 * 1024))
        throw new Error(t("Each file must be smaller than 25 MB."));
      if (
        files.some(
          (file) =>
            !/\.(png|jpe?g|gif|webp|pdf|docx|txt|md|csv|json|log)$/i.test(
              file.name,
            ),
        )
      )
        throw new Error(t("One of the file formats is not allowed."));
      let id = draftId;
      if (!id) {
        const created = await send<RequestItem>(sourceQuestion ? `/questions/${sourceQuestion}/requests` : base, {
          environment_id: Number(environment),
          need,
          confrontation,
          ...(sourceQuestion ? { source_version: sourceVersion, include_context: includeContext } : {}),
        });
        id = created.id;
        setDraftId(id);
      }
      for (let i = uploaded; i < files.length; i++) {
        const body = new FormData();
        body.append("file", files[i]);
        await api(`${base}/${id}/attachments`, { method: "POST", body });
        setUploaded(i + 1);
      }
      await send(`${base}/${id}/analyze`);
      router.push(`${base}/${id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-8">
      <div>
        <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-primary">
          {t(isQuestion ? "Explore your project" : "Your workspace")}
        </div>
        <h1>{t(isQuestion ? "Understand how your project works." : "From need to ticket, simply.")}</h1>
        <p className="muted mt-2">
          {t(
            isQuestion ? "Ask about existing behavior. SpecHelper explains it using your project sources." : "Describe your idea. SpecHelper assesses its impact and prepares an actionable ticket.",
          )}
        </p>
      </div>
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"
        >
          {t(error)}
        </div>
      )}
      <div className="grid items-start gap-7">
        <Card>
          <h2 className="flex items-center gap-2">
            <Plus size={19} className="text-primary" /> {t(isQuestion ? "New question" : "New request")}
          </h2>
          <form onSubmit={analyze}>
            <div className="field">
              <label htmlFor="environment">{t("Environment")}</label>
              <select
                id="environment"
                required
                value={environment}
                disabled={busy || !!draftId}
                onChange={(e) => setEnvironment(e.target.value)}
              >
                <option value="">{t("Choose an environment")}</option>
                {environments
                  .filter((e) => e.status === "READY")
                  .map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
              </select>
              {!environments.some((e) => e.status === "READY") && (
                <p className="mt-2 text-sm muted">
                  {t("No environment is available.")}{" "}
                  <Link href="/admin" className="text-primary underline">
                    {t("Set up the instance")}
                  </Link>
                </p>
              )}
            </div>
            <div className="field">
              <label htmlFor="need">{t(isQuestion ? "Your question" : "Describe your need")}</label>
              <Textarea
                id="need"
                required
                minLength={isQuestion ? 1 : 10}
                maxLength={30000}
                className="min-h-48"
                value={need}
                disabled={busy || !!draftId}
                onChange={(e) => setNeed(e.target.value)}
                placeholder={t(
                  isQuestion ? "How does the application validate a contract?" : "When a manager updates a contract, I would like…",
                )}
              />
              <p className="mt-2 text-xs muted">
                {t(
                  isQuestion ? "Mention the behavior, rule or part of the project you want to understand." : "Explain who is affected, the expected outcome and any special cases.",
                )}
              </p>
            </div>
            {sourceQuestion && (
              <div className="mt-5 rounded-lg border border-primary/30 p-4">
                <h3 className="text-sm">{t("Context from a question")}</h3>
                <p className="mt-2 text-sm muted">{t("Describe the change you want above. The explanation is reference material that will be checked against the selected environment.")}</p>
                <Link className="mt-2 inline-block text-sm text-primary underline" href={`/questions/${sourceQuestion}?version=${sourceVersion}`}>{t("Source question")} · {t("Version")} {sourceVersion}</Link>
                {!transfer ? <p role="status" className="mt-3 text-sm">{t("Loading question context…")}</p> : <>
                  <label className="mt-3 flex items-start gap-2 text-sm"><input type="checkbox" checked={includeContext} disabled={busy || !!draftId} onChange={e => setIncludeContext(e.target.checked)} />{t("Attach question context")}: {transfer.name}</label>
                  <p className="mt-2 text-xs muted">{includeContext ? t("This internal Markdown attachment is frozen for the new request and read only when needed.") : t("The context attachment will not be included.")}</p>
                  <details className="mt-3 text-sm"><summary className="cursor-pointer">{t("Review transferred context")}</summary><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{transfer.content}</pre></details>
                </>}
              </div>
            )}
            <div className="field">
              <label htmlFor="attachments" className="flex items-center gap-2">
                <Paperclip size={16} /> {t("Attachments")}{" "}
                <span className="font-normal muted">{t("(optional)")}</span>
              </label>
              <input
                id="attachments"
                type="file"
                multiple
                disabled={busy || !!draftId}
                accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.docx,.txt,.md,.csv,.json,.log"
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
                className="w-full text-sm file:mr-3 file:rounded-md file:border file:bg-muted file:px-3 file:py-2"
              />
              <p className="mt-2 text-xs muted">
                {t(
                  "Images, PDF, Word or text · 25 MB per file · up to 20 files.",
                )}
              </p>
            </div>
            {allowConfrontation && (
              <div className="mt-6">
                <label className="flex items-center gap-2 text-sm font-medium">
                  <input
                    type="checkbox"
                    checked={confrontation}
                    disabled={busy || !!draftId}
                    onChange={(e) => setConfrontation(e.target.checked)}
                  />
                  {t("Compare multiple analyses")}
                </label>
                <p className="mt-2 text-xs muted">
                  {t(
                    isQuestion ? "Compare two independent explanations. This option may take longer." : "Compare two independent analyses before preparing the ticket. This option may take longer.",
                  )}
                </p>
              </div>
            )}
            <Button className="mt-7 w-full" disabled={busy || !environment || (!!sourceQuestion && !transfer)}>
              <Sparkles size={17} />
              {busy
                ? t(isQuestion ? "Sending your question…" : "Sending your request…")
                : draftId
                  ? t("Resume submission")
                  : t(isQuestion ? "Analyze question" : "Analyze request")}
              <ArrowRight size={17} />
            </Button>
          </form>
        </Card>
        <div className="space-y-5">
          <Card className="border-primary/20">
            <h2>{t(isQuestion ? "An explanation grounded in your project" : "Analysis grounded in your project")}</h2>
            <ol className="mt-5 space-y-5 text-sm">
              {[
                t(isQuestion ? "You ask about the current behavior." : "You describe the desired outcome."),
                t("SpecHelper asks questions when needed."),
                t("The analysis uses your environment."),
                t(isQuestion ? "You receive an explanation with source references." : "You receive a ticket ready to share."),
              ].map((t, i) => (
                <li className="flex gap-3" key={t}>
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-primary text-xs font-bold">
                    {i + 1}
                  </span>
                  <span>{t}</span>
                </li>
              ))}
            </ol>
          </Card>
          <p className="px-2 text-sm muted">
            {t(
              isQuestion ? "Analysis may take a few minutes. You can return to your questions at any time." : "Analysis may take a few minutes. You can return to your requests at any time.",
            )}
          </p>
        </div>
      </div>
      <section>
        <h2 className="mb-4">
          {t(isQuestion ? "Questions" : "Recent requests")}{" "}
          <span className="ml-2 text-sm font-normal muted">
            {requests.length}
          </span>
        </h2>
        {requests.length ? (
          <div className="overflow-hidden rounded-xl border bg-card">
            {requests.map((r) => (
              <Link
                key={r.id}
                href={`${base}/${r.id}`}
                className="flex items-center justify-between gap-4 border-b p-5 last:border-0 hover:bg-muted"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{r.title || r.need}</p>
                  <p className="mt-1 text-xs muted">
                    {r.environment_name} ·{" "}
                    {new Date(r.created_at).toLocaleDateString(dateLocale)}
                    {isQuestion && r.updated_at && <span className="block mt-1">{t("Last updated")}: {new Date(r.updated_at).toLocaleString(dateLocale)}</span>}
                  </p>
                </div>
                <span className="badge shrink-0" data-state={r.status}>
                  {t(statuses[r.status] || r.status)}
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <Card className="py-10 text-center muted">
            {t(isQuestion ? "Your questions will appear here." : "Your requests will appear here.")}
          </Card>
        )}
      </section>
    </div>
  );
}
