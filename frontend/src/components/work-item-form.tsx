"use client";
import { useI18n } from "@/lib/i18n";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  Paperclip,
  Plus,
  Sparkles,
  FileText,
  CircleHelp,
  X,
  Search,
  SlidersHorizontal,
  ChevronDown,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { QuestionResult } from "@/components/question-result";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  send,
  statuses,
  scopeNeedsContext,
  type Environment,
  type RequestItem,
  type QuestionTransfer,
  type RequestDetail,
  type ScopeAssessment,
} from "@/lib/api";

export function WorkItemForm({
  workflow = "request",
}: {
  workflow?: "request" | "question";
}) {
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
  const [filter, setFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [preview, setPreview] = useState<RequestDetail | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [draftScope, setDraftScope] = useState<ScopeAssessment | null>(null);
  const [uploaded, setUploaded] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api<Environment[]>("/environments"), api<RequestItem[]>(base)])
      .then(([e, r]) => {
        setEnvironments(e);
        setRequests(r);
        setLoaded(true);
      })
      .catch((e) => setError(e.message));
  }, [base]);
  useEffect(() => {
    if (!sourceQuestion) {
      setTransfer(null);
      return;
    }
    let alive = true;
    setTransfer(null);
    setIncludeContext(true);
    if (!Number.isInteger(sourceVersion) || sourceVersion < 1) {
      setError(t("Choose a valid source answer version."));
      return;
    }
    api<QuestionTransfer>(
      `/questions/${sourceQuestion}/versions/${sourceVersion}/transfer`,
    )
      .then((value) => {
        if (alive) {
          setTransfer(value);
          setEnvironment(String(value.environment_id || ""));
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [sourceQuestion, sourceVersion]);
  async function analyze(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const contextFileCount = sourceQuestion && includeContext ? 1 : 0;
      if (files.length + contextFileCount > 20)
        throw new Error(
          t("A maximum of 20 attachments is allowed.") +
            (contextFileCount
              ? " " + t("The question context counts as one attachment.")
              : ""),
        );
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
      let assessment = draftScope;
      if (!id) {
        const created = await send<RequestItem>(
          sourceQuestion ? `/questions/${sourceQuestion}/requests` : base,
          {
            environment_id: environment ? Number(environment) : null,
            need,
            ...(sourceQuestion
              ? {
                  source_version: sourceVersion,
                  include_context: includeContext,
                }
              : {}),
          },
        );
        id = created.id;
        assessment = created.scope_assessment || null;
        setDraftId(id);
        setDraftScope(assessment);
      }
      for (let i = uploaded; i < files.length; i++) {
        const body = new FormData();
        body.append("file", files[i]);
        await api(`${base}/${id}/attachments`, { method: "POST", body });
        setUploaded(i + 1);
      }
      if (!scopeNeedsContext(assessment)) await send(`${base}/${id}/analyze`);
      router.push(`${base}/${id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const filtered = requests.filter(
    (item) =>
      (!statusFilter || item.status === statusFilter) &&
      `${item.title || ""} ${item.need} ${item.environment_name}`
        .toLocaleLowerCase(dateLocale)
        .includes(filter.toLocaleLowerCase(dateLocale)),
  );
  useEffect(() => {
    if (!previewId) return;
    let alive = true;
    setPreview(null);
    setPreviewError("");
    api<RequestDetail>(`/questions/${previewId}`)
      .then((value) => {
        if (alive) setPreview(value);
      })
      .catch((e) => {
        if (alive) setPreviewError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [previewId]);
  function addFiles(items: File[]) {
    setFiles((current) => [
      ...current,
      ...items.filter(
        (item) =>
          !current.some(
            (old) =>
              old.name === item.name &&
              old.size === item.size &&
              old.lastModified === item.lastModified,
          ),
      ),
    ]);
  }
  function reset() {
    if (busy || draftId) return;
    setNeed("");
    setFiles([]);
    setError("");
    if (!sourceQuestion) setEnvironment("");
    const input = document.getElementById(
      "attachments",
    ) as HTMLInputElement | null;
    if (input) input.value = "";
  }
  const PageIcon = isQuestion ? CircleHelp : FileText;
  return (
    <div className="space-y-6">
      <header className="page-heading">
        <div className="page-title">
          <span className="page-icon">
            <PageIcon size={20} />
          </span>
          <div>
            <h1>{t(isQuestion ? "Questions" : "Requests")}</h1>
            <p className="muted">
              {t(
                isQuestion
                  ? "Ask a question or explore your previous explanations."
                  : "Create a request or review your existing analyses.",
              )}
            </p>
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          aria-label={t(isQuestion ? "New question" : "New request")}
          onClick={() => {
            document
              .getElementById("create-work-item")
              ?.scrollIntoView({ block: "start" });
            document.getElementById("need")?.focus();
          }}
        >
          <Plus size={16} />
          <span>{t(isQuestion ? "New question" : "New request")}</span>
        </Button>
      </header>
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"
        >
          {t(error)}
        </div>
      )}
      <Card id="create-work-item">
        <div className="section-heading">
          <h2>
            <PageIcon size={18} />
            {t(isQuestion ? "New question" : "New request")}
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy || !!draftId}
            onClick={reset}
          >
            {t("Clear form")}
          </Button>
        </div>
        <form onSubmit={analyze}
          onDragOver={(event) => {
            if (!Array.from(event.dataTransfer.types).includes("Files")) return;
            event.preventDefault();
            if (!busy && !draftId) setDragging(true);
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
          }}
          onDrop={(event) => {
            if (!Array.from(event.dataTransfer.types).includes("Files")) return;
            event.preventDefault();
            setDragging(false);
            if (!busy && !draftId) addFiles(Array.from(event.dataTransfer.files));
          }}
        >
          <div className="form-top-row">
            <div>
              <label htmlFor="environment">{t("Environment")}</label>
              <select
                id="environment"
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
              <p className="mt-2 text-xs muted">{t("Choose the project environment when known. You can clarify it before analysis.")}</p>
              {loaded && !environments.some((e) => e.status === "READY") && (
                <p className="mt-2 text-xs muted">
                  {t("No environment is available.")}{" "}
                  <Link href="/admin" className="text-primary underline">
                    {t("Set up the instance")}
                  </Link>
                </p>
              )}
            </div>

          </div>
          <div className="field">
            <label htmlFor="need">
              {t(isQuestion ? "Your question" : "Describe your need")}
            </label>
            <Textarea
              id="need"
              required
              minLength={1}
              maxLength={30000}
              className="min-h-36"
              value={need}
              disabled={busy || !!draftId}
              onChange={(e) => setNeed(e.target.value)}
              placeholder={t(
                isQuestion
                  ? "How does the application validate a contract?"
                  : "When a manager updates a contract, I would like…",
              )}
            />
            <div className="mt-2 flex justify-between gap-3 text-xs muted">
              <p>
                {t(
                  isQuestion
                    ? "Mention the behavior, rule or part of the project you want to understand."
                    : "Explain who is affected, the expected outcome and any special cases.",
                )}
              </p>
              <span className="shrink-0">{need.length} / 30 000</span>
            </div>
          </div>
          {sourceQuestion && (
            <div className="mt-5 rounded-lg border p-4">
              <h3 className="text-sm">{t("Context from a question")}</h3>
              <p className="mt-2 text-sm muted">
                {t(
                  "Describe the change you want above. The explanation is reference material that will be checked against the selected environment.",
                )}
              </p>
              <Link
                className="mt-2 inline-block text-sm text-primary underline"
                href={`/questions/${sourceQuestion}?version=${sourceVersion}`}
              >
                {t("Source question")} · {t("Version")} {sourceVersion}
              </Link>
              {!transfer ? (
                <p role="status" className="mt-3 text-sm">
                  {t("Loading question context…")}
                </p>
              ) : (
                <>
                  <label className="mt-3 flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={includeContext}
                      disabled={busy || !!draftId}
                      onChange={(e) => setIncludeContext(e.target.checked)}
                    />
                    {t("Attach question context")}: {transfer.name}
                  </label>
                  <p className="mt-2 text-xs muted">
                    {t(
                      includeContext
                        ? "This internal Markdown attachment is frozen for the new request and read only when needed."
                        : "The context attachment will not be included.",
                    )}
                  </p>
                  <details className="mt-3 text-sm">
                    <summary className="cursor-pointer">
                      {t("Review transferred context")}
                    </summary>
                    <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">
                      {transfer.content}
                    </pre>
                  </details>
                </>
              )}
            </div>
          )}
          <div className="field">
            <label
              htmlFor="attachments"
              id="attachments-label"
              className="flex items-center gap-2"
            >
              <Paperclip size={15} />
              {t("Attachments")}{" "}
              <span className="font-normal muted">{t("(optional)")}</span>
            </label>
            <div
              className={`flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2 ${dragging ? "border-primary bg-primary/10" : "border-dashed"}`}
              data-dragging={dragging}
            >
              <input
                id="attachments"
                className="sr-only peer"
                type="file"
                multiple
                disabled={busy || !!draftId}
                accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.docx,.txt,.md,.csv,.json,.log"
                aria-describedby="attachment-limits attachment-feedback"
                onChange={(e) => { addFiles(Array.from(e.target.files || [])); e.target.value = ""; }}
              />
              <label htmlFor="attachments" style={{ display: "inline-flex", whiteSpace: "nowrap" }} className={`!mb-0 inline-flex cursor-pointer items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary ${busy || draftId ? "pointer-events-none opacity-50" : ""}`}>
                <Paperclip size={15} aria-hidden="true" />{t("Add files")}
              </label>
              <span className="text-xs muted">{t("25 MB · 20 files")}</span>
            </div>
            <p id="attachment-limits" className="mt-2 text-xs muted">
              {t("Images, PDF, Word or text · 25 MB per file · up to 20 files.")}
              <span className="block">{t("You can also drop files anywhere on this form.")}</span>
            </p>
            <p id="attachment-feedback" role="status" className="sr-only">{t("{count} files selected", { count: files.length })}</p>
            {files.length + (sourceQuestion && includeContext ? 1 : 0) > 20 && <p role="alert" className="mt-2 text-sm text-red-700">{t("A maximum of 20 attachments is allowed.")}</p>}
            {!!files.length && (
              <ul className="file-selection">
                {files.map((file, index) => (
                  <li key={`${file.name}-${index}`}>
                    <Paperclip size={13} />
                    <span className="min-w-0 flex-1 break-words">{file.name}<span className="ml-2 text-xs muted">{file.size < 1024 * 1024 ? `${Math.ceil(file.size / 1024)} KB` : `${(file.size / (1024 * 1024)).toFixed(1)} MB`}</span>
                      {file.size > 25 * 1024 * 1024 && <span role="alert" className="block text-xs text-red-700">{t("Each file must be smaller than 25 MB.")}</span>}
                      {!/\.(png|jpe?g|gif|webp|pdf|docx|txt|md|csv|json|log)$/i.test(file.name) && <span role="alert" className="block text-xs text-red-700">{t("One of the file formats is not allowed.")}</span>}
                    </span>
                    <button
                      type="button"
                      aria-label={t("Remove file {name}", { name: file.name })}
                      disabled={busy || !!draftId}
                      onClick={() =>
                        setFiles((value) => value.filter((_, i) => i !== index))
                      }
                    >
                      <X size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="form-actions">
            <p className="muted">
              {t(
                isQuestion
                  ? "Analysis may take a few minutes. You can return to your questions at any time."
                  : "Analysis may take a few minutes. You can return to your requests at any time.",
              )}
            </p>
            <Button
              disabled={busy || (!!sourceQuestion && !transfer)}
            >
              <Sparkles size={16} />
              {busy
                ? t(
                    isQuestion
                      ? "Sending your question…"
                      : "Sending your request…",
                  )
                : draftId
                  ? t("Resume submission")
                  : t(isQuestion ? "Analyze question" : "Analyze request")}
              <ArrowRight size={16} />
            </Button>
          </div>
        </form>
      </Card>
      <section className="overflow-hidden rounded-xl border bg-card">
        <div className="work-list-header">
          <h2>
            <PageIcon size={17} />
            {t(isQuestion ? "My questions" : "My requests")}
            <span className="text-xs font-normal muted">{requests.length}</span>
          </h2>
          <div className="work-list-search">
            <div className="relative min-w-0">
              <Search size={14} className="absolute left-3 top-3 muted" />
              <Input
                className="pl-9"
                aria-label={t(
                  isQuestion ? "Search questions" : "Search requests",
                )}
                placeholder={t(
                  isQuestion ? "Search questions" : "Search requests",
                )}
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-expanded={showFilters}
              onClick={() => setShowFilters((value) => !value)}
            >
              <SlidersHorizontal size={14} />
              {t("Filters")}
            </Button>
          </div>
        </div>
        {showFilters && (
          <div className="work-list-filters">
            <label htmlFor="work-status">{t("Filter by status")}</label>
            <select
              id="work-status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">{t("All statuses")}</option>
              {Array.from(new Set(requests.map((item) => item.status))).map(
                (status) => (
                  <option key={status} value={status}>
                    {t(statuses[status] || status)}
                  </option>
                ),
              )}
            </select>
          </div>
        )}
        {!loaded && !error && (
          <p role="status" className="p-8 text-center muted">
            {t("Loading…")}
          </p>
        )}
        {loaded && !filtered.length && (
          <p className="p-8 text-center text-sm muted">
            {t(
              requests.length
                ? isQuestion
                  ? "No questions match these filters."
                  : "No requests match these filters."
                : isQuestion
                  ? "Your questions will appear here."
                  : "Your requests will appear here.",
            )}
          </p>
        )}
        {filtered.map((item) => (
          <article className="work-list-row" key={item.id}>
            <div className="work-list-main">
              <div className="min-w-0 flex-1">
                <Link className="work-list-title" href={`${base}/${item.id}`}>
                  {item.title || item.need}
                </Link>
                <p className="row-subtitle">
                  {item.environment_name} ·{" "}
                  {new Date(item.created_at).toLocaleDateString(dateLocale)}
                </p>
                {item.updated_at && (
                  <p className="row-subtitle">
                    {t("Last updated")}:{" "}
                    {new Date(item.updated_at).toLocaleString(dateLocale)}
                  </p>
                )}
              </div>
              <span className="badge shrink-0" data-state={item.status}>
                {t(statuses[item.status] || item.status)}
              </span>
              {isQuestion && ["READY", "PARTIAL"].includes(item.status) && (
                <button
                  type="button"
                  className="p-2"
                  aria-label={t(
                    previewId === item.id
                      ? "Hide answer"
                      : "Preview answer {title}",
                    { title: item.title || item.need },
                  )}
                  aria-expanded={previewId === item.id}
                  onClick={() => {
                    setPreview(null);
                    setPreviewError("");
                    setPreviewId((value) =>
                      value === item.id ? null : item.id,
                    );
                  }}
                >
                  <ChevronDown size={16} />
                </button>
              )}
            </div>
            {previewId === item.id && (
              <div className="mt-5 space-y-4">
                {previewError ? (
                  <p role="alert" className="text-sm text-red-700">
                    {t(previewError)}
                  </p>
                ) : !preview ? (
                  <p role="status" className="muted text-sm">
                    {t("Loading…")}
                  </p>
                ) : preview.latest_version ? (
                  <QuestionResult
                    key={`${item.id}-${preview.latest_version.number}`}
                    questionId={item.id}
                    result={preview.latest_version}
                    versions={preview.versions}
                    latestNumber={preview.latest_version.number}
                    selectedNumber={null}
                    onSelect={(number) =>
                      router.push(
                        `/questions/${item.id}${number ? `?version=${number}` : ""}`,
                      )
                    }
                  />
                ) : (
                  <Link
                    href={`/questions/${item.id}`}
                    className="text-primary underline"
                  >
                    {t("Open question")}
                  </Link>
                )}
              </div>
            )}
          </article>
        ))}
      </section>
    </div>
  );
}
