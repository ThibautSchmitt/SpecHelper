"use client";
import { useEffect, useRef, useState } from "react";
import { ProviderLogo } from "@/components/provider-logo";
import { SafeMarkdown } from "@/components/safe-markdown";
import { secureFetch } from "@/lib/access";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  type TicketConnector,
  type Destination,
} from "@/components/ticket-connectors";

type Option = { id: string; name: string };
type Field = {
  id: string;
  label: string;
  type: string;
  required: boolean;
  options: Option[];
  default?: unknown;
  description?: string;
  read_only?: boolean;
};
type Presentation = {
  ticket_format: "" | "project" | "standard";
  include_business_analysis: boolean;
  include_technical_analysis: boolean;
  include_attachments: boolean;
  attachment_ids: string[];
  include_goal: boolean;
  include_diagrams: boolean;
};
type TransferFile = { id: string; name: string; size: number; mime: string; kind: "original" | "goal" | "diagrams"; transferable: boolean; reason?: string; };
const defaultPresentation: Presentation = { ticket_format: "", include_business_analysis: false, include_technical_analysis: false, include_attachments: false, attachment_ids: [], include_goal: false, include_diagrams: false };
type Preview = Partial<Presentation> & {
  draft_id?: string;
  draft_revision?: number;
  template_id?: string;
  issue_type?: string;
  fallback_reason?: string;
  publication_allowed?: boolean;
  publication_blockers?: string[];
  validation_errors?: Record<string, string>;
  available_attachments?: TransferFile[];
  selected_attachments?: TransferFile[];
  result_status?: string;
  version_id?: string;
  environment_name?: string;
  baseline?: { repository: string; sha: string; branch?: string }[];
  publication_reference?: string;
  rendered_body?: string;
  title: string;
  body: string;
  fields: Field[];
  labels: Option[];
  assignees: Option[];
  templates: Option[];
  issue_types: Option[];
  revision: string;
  format: string;
  render_fields?: boolean;
  notice?: string;
  values: Record<string, unknown>;
  defaults?: { labels?: string[]; assignees?: string[] };
};
type Publication = {
  id: string;
  status: string;
  url?: string;
  external_id?: string;
  external_key?: string;
  error?: string;
  attachment_delivery?: { id: string; name: string; status: "TRANSFERRING" | "TRANSFERRED" | "UNCERTAIN"; error?: string; external_id?: string }[];
};
type Payload = Partial<Presentation> & {
  draft_id?: string;
  draft_revision?: number;
  connector_id: number;
  project: string;
  title: string;
  body: string;
  fields: Record<string, unknown>;
  labels: string[];
  assignees: string[];
  template_id: string;
  issue_type: string;
  options_revision: string;
  idempotency_key: string;
  confirmed: boolean;
};
type Attempt = Publication & {
  connector_id: number;
  project: string;
  idempotency_key: string;
  snapshot: Omit<
    Payload,
    "connector_id" | "project" | "idempotency_key" | "confirmed"
  >;
};

function remember(key: string, payload: Payload | null) {
  try {
    if (payload) sessionStorage.setItem(key, JSON.stringify(payload));
    else sessionStorage.removeItem(key);
  } catch {}
}

export function PublishTicket({
  requestId,
  version,
}: {
  requestId: string;
  version: number;
}) {
  const { t } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [connectors, setConnectors] = useState<TicketConnector[]>([]);
  const [connector, setConnector] = useState("");
  const [projects, setProjects] = useState<Destination[]>([]);
  const [project, setProject] = useState("");
  const [template, setTemplate] = useState("");
  const [issueType, setIssueType] = useState("");
  const [presentation, setPresentation] = useState<Presentation>(defaultPresentation);
  const previewGeneration = useRef(0);
  const [saved, setSaved] = useState(false);
  const [draftSaveFailed, setDraftSaveFailed] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [fields, setFields] = useState<Record<string, unknown>>({});
  const [labels, setLabels] = useState<string[]>([]);
  const [assignees, setAssignees] = useState<string[]>([]);
  const [recovering, setRecovering] = useState(false);
  const [recoveryFailed, setRecoveryFailed] = useState(false);
  const [recoveryGeneration, setRecoveryGeneration] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Publication | null>(null);
  const [pending, setPending] = useState<Payload | null>(null);
  const storageKey = `publication:${requestId}:${version}`;
  const endpoint = `/requests/${requestId}/versions/${version}`;
  useEffect(() => {
    if (!open) return;
    let alive = true;
    setError("");
    setRecovering(true);
    setRecoveryFailed(false);
    let storedKey: string | undefined;
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) {
        const payload = JSON.parse(saved);
        setPending(payload);
        storedKey = payload.idempotency_key;
      }
    } catch {}
    api<Attempt[]>(`${endpoint}/publications`)
      .then((attempts) => {
        if (!alive) return;
        const unfinished = attempts.find((p) =>
          ["UNCERTAIN", "PUBLISHING"].includes(p.status),
        );
        if (unfinished) {
          const payload = {
            ...unfinished.snapshot,
            connector_id: unfinished.connector_id,
            project: unfinished.project,
            idempotency_key: unfinished.idempotency_key,
            confirmed: true,
          };
          setPending(payload);
          remember(storageKey, payload);
          setResult(unfinished);
        } else {
          const previous = attempts.find(
            (p) => p.idempotency_key === storedKey,
          );
          if (previous && ["PUBLISHED", "ERROR"].includes(previous.status)) {
            setPending(null);
            remember(storageKey, null);
            setResult(previous);
            if (previous.status === "ERROR")
              setError(
                previous.error ||
                  "Publication failed. Verify the destination before retrying.",
              );
          }
        }
      })
      .catch((e) => {
        if (alive) {
          setError(e.message);
          setRecoveryFailed(true);
        }
      })
      .finally(() => {
        if (alive) setRecovering(false);
      });
    api<TicketConnector[]>(`/ticket-connectors?request_id=${requestId}`)
      .then((v) => {
        if (alive) {
          const available = v.filter(
            (c) => c.status === "CONNECTED" && c.projects.length,
          );
          setConnectors(available);
          setConnector(available[0] ? String(available[0].id) : "");
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [open, storageKey, endpoint, recoveryGeneration]);
  useEffect(() => {
    if (!open || !connector) return;
    let alive = true;
    setPreview(null);
    setProjects([]);
    setProject("");
    setTemplate("");
    setIssueType("");
    const current = connectors.find((c) => String(c.id) === connector);
    api<Destination[]>(`/ticket-connectors/${connector}/projects`)
      .then((v) => {
        if (alive) {
          const allowed = v.filter((p) => current?.projects.includes(p.id));
          setProjects(allowed);
          setProject(
            allowed.find((p) => p.id === current?.default_project)?.id ||
              allowed[0]?.id ||
              "",
          );
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [open, connector, connectors]);
  function applyPreview(value: Preview) {
    setPreview(value);
    setTitle(value.title);
    setBody(value.body);
    setTemplate(value.template_id || "");
    setIssueType(value.issue_type || "");
    setPresentation({ ...defaultPresentation, ...Object.fromEntries(Object.keys(defaultPresentation).filter(key => key in value).map(key => [key, value[key as keyof Preview]])) });
    setFields({ ...Object.fromEntries(value.fields.map(field => [field.id, field.default ?? (field.type === "checkboxes" ? [] : "")])), ...value.values });
    setLabels(value.defaults?.labels || []);
    setAssignees(value.defaults?.assignees || []);
    setDirty(false);
    setSaved(false);
    setDraftSaveFailed(false);
  }
  useEffect(() => {
    if (!open || !connector || !project) return;
    const generation = ++previewGeneration.current;
    setBusy(true);
    setError("");
    setPreview(null);
    api<Preview>(`${endpoint}/publication-draft?connector_id=${connector}&project=${encodeURIComponent(project)}`)
      .then(value => { if (generation === previewGeneration.current) applyPreview(value); })
      .catch(error => { if (generation === previewGeneration.current) setError(error.message); })
      .finally(() => { if (generation === previewGeneration.current) setBusy(false); });
    return () => { previewGeneration.current++; };
  }, [open, connector, project, endpoint]);
  async function recompose(changes: Partial<Presentation> & { template_id?: string; issue_type?: string }) {
    const generation = ++previewGeneration.current;
    const before = presentation;
    const previousTemplate = template;
    const previousType = issueType;
    setPresentation(current => ({ ...current, ...Object.fromEntries(Object.keys(defaultPresentation).filter(key => key in changes).map(key => [key, changes[key as keyof typeof changes]])) }));
    if (changes.template_id !== undefined) setTemplate(changes.template_id);
    if (changes.issue_type !== undefined) setIssueType(changes.issue_type);
    setBusy(true);
    setError("");
    try {
      const value = await send<Preview>(`${endpoint}/publication-preview`, { connector_id: Number(connector), project, template_id: template, issue_type: issueType, ...presentation, ...changes });
      if (generation === previewGeneration.current) applyPreview(value);
    } catch (error) {
      if (generation === previewGeneration.current) { setPresentation(before); setTemplate(previousTemplate); setIssueType(previousType); setError((error as Error).message); }
    } finally {
      if (generation === previewGeneration.current) setBusy(false);
    }
  }
  function draftPayload() {
    return { connector_id: Number(connector), project, title, body, fields, labels, assignees, template_id: template, issue_type: issueType, options_revision: preview?.revision, draft_id: preview?.draft_id, draft_revision: preview?.draft_revision, ...presentation };
  }
  async function saveDraft() {
    try {
      const value = await send<Preview>(`${endpoint}/publication-draft?connector_id=${connector}&project=${encodeURIComponent(project)}`, draftPayload(), "PUT");
      setPreview(value);
      setDirty(false);
      setSaved(true);
      setDraftSaveFailed(false);
      return value;
    } catch (error) {
      setDraftSaveFailed(true);
      throw error;
    }
  }
  async function reloadDraft() {
    const generation = ++previewGeneration.current;
    setBusy(true);
    setError("");
    try {
      const value = await api<Preview>(`${endpoint}/publication-draft?connector_id=${connector}&project=${encodeURIComponent(project)}`);
      if (generation === previewGeneration.current) applyPreview(value);
    } catch (error) {
      if (generation === previewGeneration.current) setError((error as Error).message);
    } finally {
      if (generation === previewGeneration.current) setBusy(false);
    }
  }
  const fieldBody = preview?.render_fields
    ? (
        body +
        preview.fields
          .map((field) => {
            const value = fields[field.id] ?? field.default ?? "";
            const text = Array.isArray(value)
              ? value.join(", ")
              : typeof value === "boolean"
                ? value
                  ? "[x]"
                  : "[ ]"
                : String(value);
            return `\n\n### ${field.label}\n\n${text}`;
          })
          .join("")
      ).trim()
    : body;
  const reference = preview?.publication_reference || "";
  const referencePattern = reference
    ? new RegExp(`(?<![\\w:.-])${reference.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w:.-])`)
    : null;
  const renderedBody = reference && !referencePattern?.test(fieldBody)
    ? `${fieldBody}\n\n${reference}`.trim()
    : fieldBody.trim();
  function change(action: () => void) {
    if (
      !dirty ||
      window.confirm(
        t(
          "Changing the destination or template will replace your edits. Continue?",
        ),
      )
    ) {
      setDirty(false);
      action();
    }
  }
  async function publish(payload: Payload) {
    setBusy(true);
    setError("");
    setPending(payload);
    remember(storageKey, payload);
    try {
      const response = await secureFetch(`/api${endpoint}/publications`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        if (
          response.status === 409 &&
          /options.*changed|template.*changed/i.test(String(data.detail))
        ) {
          setError(
            typeof data.detail === "string"
              ? data.detail
              : "Publication options changed. Review the current fields before creating the ticket.",
          );
          setPending(null);
          remember(storageKey, null);
          setPreview(null);
        } else {
          setError(
            typeof data.detail === "string"
              ? data.detail
              : "Publication failed. Verify the destination before retrying.",
          );
          if (response.status === 409) {
            const attempts = await api<Attempt[]>(`${endpoint}/publications`);
            const existing = attempts.find(
              (attempt) =>
                attempt.connector_id === payload.connector_id &&
                attempt.project === payload.project,
            );
            if (existing?.status === "PUBLISHED") {
              setResult(existing);
              setPending(null);
              remember(storageKey, null);
              setError("");
            } else if (
              existing &&
              ["UNCERTAIN", "PUBLISHING"].includes(existing.status)
            ) {
              const original = {
                ...existing.snapshot,
                connector_id: existing.connector_id,
                project: existing.project,
                idempotency_key: existing.idempotency_key,
                confirmed: true,
              };
              setResult(existing);
              setPending(original);
              remember(storageKey, original);
            } else {
              setPending(null);
              remember(storageKey, null);
              setPreview(null);
            }
          }
          if (response.status < 500 && response.status !== 409) {
            setPending(null);
            remember(storageKey, null);
          }
        }
        return;
      }
      setResult(data);
      if (["PUBLISHED", "ERROR"].includes(data.status)) {
        setPending(null);
        remember(storageKey, null);
      }
      if (data.status === "ERROR")
        setError(
          data.error ||
            "Publication failed. Verify the destination before retrying.",
        );
    } catch {
      setError(
        "The publication outcome is unknown. Verify before retrying to avoid duplicates.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function close() {
    if (busy) return;
    if (dirty && preview) {
      setBusy(true);
      try { await saveDraft(); }
      catch (error) { setError((error as Error).message); return; }
      finally { setBusy(false); }
    }
    finishClose();
  }
  function finishClose() {
    previewGeneration.current++;
    dialog.current?.close();
    setOpen(false);
    setPreview(null);
    setResult(null);
    setDirty(false);
    setConnector("");
    setPending(null);
    setDraftSaveFailed(false);
  }
  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          setOpen(true);
          dialog.current?.showModal();
        }}
      >
        {t("Prepare ticket")}
      </Button>
      <dialog
        ref={dialog}
        className="publication-dialog"
        aria-labelledby={`publication-title-${version}`}
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id={`publication-title-${version}`}>{t("Publish ticket")}</h2>
            <p className="mt-1 text-sm muted">
              {t(
                "Publish analysis version {number}. The saved analysis will remain unchanged.",
                { number: version },
              )}
            </p>
          </div>
          <Button type="button" variant="ghost" onClick={close}>
            {t("Close")}
          </Button>
        </div>
        {error && (
          <p
            role="alert"
            className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-red-800"
          >
            {t(error)}
          </p>
        )}
        {recovering ? (
          <p role="status" className="mt-5">
            {t("Checking previous publications…")}
          </p>
        ) : recoveryFailed ? (
          <div className="mt-5">
            <p className="mb-4">
              {t(
                "Previous publications could not be checked. Check again before creating a ticket.",
              )}
            </p>
            <Button onClick={() => setRecoveryGeneration((v) => v + 1)}>
              {t("Check publications again")}
            </Button>
          </div>
        ) : result?.status === "PUBLISHED" ? (
          <div className="mt-6">
            <p role="status" className="text-green-800">
              {t("Ticket published successfully.")}{" "}
              {result.external_key || result.external_id}
            </p>
            {!!result.attachment_delivery?.length && <section className="mt-4 space-y-3 text-sm" aria-label={t("Attachment transfer results")}>
              <h3>{t("Attachment transfer results")}</h3>
              {result.attachment_delivery.map(file => <div key={file.id} className="rounded border p-3"><p className="break-words font-medium">{file.name} · {t(file.status === "TRANSFERRED" ? "File transferred" : file.status === "TRANSFERRING" ? "File transfer in progress" : "File transfer outcome unknown")}</p>{file.error && <p role="alert" className="mt-1 break-words">{t(file.error)}</p>}{file.status === "UNCERTAIN" && <p className="mt-1 muted">{t("Check the destination before transferring this file again.")}</p>}</div>)}
            </section>}
            {result.url && (
              <a
                className="mt-4 inline-block text-primary underline"
                href={result.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("Open ticket")}
              </a>
            )}
          </div>
        ) : pending ? (
          <div className="mt-6 space-y-4">
            <p role="status">
              {t(
                "The publication outcome is unknown. Verify before retrying to avoid duplicates.",
              )}
            </p>
            <p className="text-sm muted">
              {t(
                "Verification reuses the same publication reference and content.",
              )}
            </p>
            <Button disabled={busy} onClick={() => publish(pending)}>
              {busy ? t("Verifying…") : t("Verify publication")}
            </Button>
          </div>
        ) : (
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              if (!preview || preview.publication_allowed === false) return;
              setBusy(true);
              let current = preview;
              try { current = await saveDraft(); }
              catch (error) { setError((error as Error).message); setBusy(false); return; }
              publish({
                ...presentation,
                draft_id: current.draft_id,
                draft_revision: current.draft_revision,
                connector_id: Number(connector),
                project,
                title,
                body,
                fields,
                labels,
                assignees,
                template_id: template,
                issue_type: issueType,
                options_revision: preview.revision,
                idempotency_key: crypto.randomUUID(),
                confirmed: true,
              });
            }}
          >
            {!connectors.length && (
              <p className="mt-5 muted">
                {t(
                  "No connected publication destination is configured. Configure a connector and allowed projects in Settings.",
                )}
              </p>
            )}
            <fieldset disabled={busy} className="grid gap-x-4 sm:grid-cols-2">
              <div className="field">
                <label htmlFor="publish-connector">{t("Connector")}</label>
                <select
                  id="publish-connector"
                  required
                  value={connector}
                  onChange={(e) => change(() => setConnector(e.target.value))}
                >
                  <option value="">{t("Select a connector")}</option>
                  {connectors.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="publish-project">
                  {t("Project / repository")}
                </label>
                <select
                  id="publish-project"
                  required
                  value={project}
                  onChange={(e) =>
                    change(() => {
                      setProject(e.target.value);
                      setTemplate("");
                      setIssueType("");
                    })
                  }
                >
                  <option value="">{t("Select a project")}</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
              {preview && <div className="field sm:col-span-2">
                <label htmlFor="publish-format">{t("Ticket format")}</label>
                <select id="publish-format" value={presentation.ticket_format || "standard"} onChange={event => change(() => { void recompose({ ticket_format: event.target.value as "project" | "standard", ...(event.target.value === "project" ? { include_diagrams: false } : {}) }); })}>
                  <option value="project" disabled={!preview.templates.length}>{t("Project template")}</option>
                  <option value="standard">{t("Standard SpecHelper format")}</option>
                </select>
                {preview.fallback_reason && <p role="status" className="mt-2 text-xs muted">{t(preview.fallback_reason)}</p>}
              </div>}
              {!!preview?.templates.length && (
                <div className="field">
                  <label htmlFor="publish-template">
                    {t("Ticket template")}
                  </label>
                  <select
                    id="publish-template"
                    value={template}
                    required={presentation.ticket_format === "project"}
                    disabled={presentation.ticket_format === "standard"}
                    onChange={(e) => change(() => { void recompose({ template_id: e.target.value }); })}
                  >
                    <option value="">{t("Select a template")}</option>
                    {preview.templates.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {!!preview?.issue_types.length && (
                <div className="field">
                  <label htmlFor="publish-issue-type">{t("Issue type")}</label>
                  <select
                    id="publish-issue-type"
                    required
                    value={issueType}
                    onChange={(e) => change(() => { void recompose({ issue_type: e.target.value }); })}
                  >
                    <option value="">{t("Select an issue type")}</option>
                    {preview.issue_types.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </fieldset>
            {busy && (
              <p role="status" className="mt-4">
                {t("Loading publication options…")}
              </p>
            )}
            {!preview && !!project && !busy && (
              <Button
                type="button"
                className="mt-4"
                variant="outline"
                onClick={() => {
                  void recompose({});
                }}
              >
                {t("Reload and review options")}
              </Button>
            )}
            {preview && (
              <fieldset disabled={busy}>
                {preview.notice && (
                  <p className="mt-4 rounded border bg-muted p-3 text-sm">
                    {t(preview.notice)}
                  </p>
                )}
                {preview.publication_allowed === false && <div role="status" className="mt-4 rounded-lg border border-amber-500/50 p-4 text-sm">
                  <p className="font-semibold">{t("Publication is blocked")}</p>
                  <ul className="mt-2 list-disc pl-5">{(preview.publication_blockers?.length ? preview.publication_blockers : ["Required independent checks are incomplete. Publication is blocked."]).map((reason, index) => <li key={index}>{t(reason)}</li>)}</ul>
                  <p className="mt-2 muted">{t("You can review and save this draft. Exporting it does not complete the missing checks.")}</p>
                </div>}
                <fieldset className="mt-5 space-y-3 rounded-lg border p-4">
                  <legend className="px-1 text-sm font-semibold">{t("Optional ticket content")}</legend>
                  {([["include_business_analysis", "Include detailed business analysis"], ["include_technical_analysis", "Include detailed technical analysis"]] as const).map(([key, label]) => <label key={key} className="flex items-start gap-2 text-sm"><input type="checkbox" checked={presentation[key]} onChange={event => change(() => { void recompose({ [key]: event.target.checked }); })} />{t(label)}</label>)}
                  <p className="text-xs muted">{t("These options change only the ticket presentation. The verified analysis and detailed goal.md remain unchanged.")}</p>
                </fieldset>
                <div className="field">
                  <label htmlFor="publish-title">{t("Ticket title")}</label>
                  <Input
                    id="publish-title"
                    required
                    value={title}
                    onChange={(e) => {
                      setTitle(e.target.value);
                      setDirty(true);
                    }}
                  />
                </div>
                <div className="field">
                  <label htmlFor="publish-body">
                    {t("Ticket description")}
                  </label>
                  <Textarea
                    id="publish-body"
                    required={!preview.render_fields}
                    className="min-h-52"
                    value={body}
                    onChange={(e) => {
                      setBody(e.target.value);
                      setDirty(true);
                    }}
                  />
                </div>
                {preview.fields.map((field) => (
                  <div key={field.id} className="field">
                    <label htmlFor={`publish-field-${field.id}`}>
                      {field.label}
                      {field.required ? " *" : ""}
                    </label>
                    {field.description && (
                      <p className="mb-2 text-xs muted">{field.description}</p>
                    )}
                    {field.type === "checkbox" ? (
                      <input
                        id={`publish-field-${field.id}`}
                        disabled={field.read_only}
                        type="checkbox"
                        required={field.required}
                        checked={Boolean(fields[field.id])}
                        onChange={(e) => {
                          setFields({
                            ...fields,
                            [field.id]: e.target.checked,
                          });
                          setDirty(true);
                        }}
                      />
                    ) : field.type === "textarea" ? (
                      <Textarea
                        id={`publish-field-${field.id}`}
                        disabled={field.read_only}
                        required={field.required}
                        value={String(fields[field.id] ?? "")}
                        onChange={(e) => {
                          setFields({ ...fields, [field.id]: e.target.value });
                          setDirty(true);
                        }}
                      />
                    ) : field.options?.length ? (
                      <select
                        id={`publish-field-${field.id}`}
                        disabled={field.read_only}
                        required={field.required}
                        multiple={["checkboxes", "multiselect"].includes(
                          field.type,
                        )}
                        value={
                          Array.isArray(fields[field.id])
                            ? (fields[field.id] as string[])
                            : String(fields[field.id] ?? "")
                        }
                        onChange={(e) => {
                          setFields({
                            ...fields,
                            [field.id]: e.target.multiple
                              ? Array.from(
                                  e.target.selectedOptions,
                                  (o) => o.value,
                                )
                              : e.target.value,
                          });
                          setDirty(true);
                        }}
                      >
                        {!["checkboxes", "multiselect"].includes(
                          field.type,
                        ) && <option value="">{t("Select a value")}</option>}
                        {field.options.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        id={`publish-field-${field.id}`}
                        disabled={field.read_only}
                        required={field.required}
                        type={
                          field.type === "number"
                            ? "number"
                            : field.type === "date"
                              ? "date"
                              : "text"
                        }
                        value={String(fields[field.id] ?? "")}
                        onChange={(e) => {
                          setFields({ ...fields, [field.id]: e.target.value });
                          setDirty(true);
                        }}
                      />
                    )}
                  </div>
                ))}
                {!!preview.labels.length && (
                  <div className="field">
                    <label htmlFor="publish-labels">{t("Labels")}</label>
                    <select
                      id="publish-labels"
                      multiple
                      value={labels}
                      onChange={(e) => {
                        setLabels(
                          Array.from(e.target.selectedOptions, (o) => o.value),
                        );
                        setDirty(true);
                      }}
                    >
                      {preview.labels.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                {!!preview.assignees.length && (
                  <div className="field">
                    <label htmlFor="publish-assignees">{t("Assignees")}</label>
                    <select
                      id="publish-assignees"
                      multiple
                      value={assignees}
                      onChange={(e) => {
                        setAssignees(
                          Array.from(e.target.selectedOptions, (o) => o.value),
                        );
                        setDirty(true);
                      }}
                    >
                      {preview.assignees.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <fieldset className="mt-5 space-y-3 rounded-lg border p-4">
                  <legend className="px-1 text-sm font-semibold">{t("Files to transfer")}</legend>
                  <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={presentation.include_attachments} onChange={event => change(() => { void recompose({ include_attachments: event.target.checked, ...(event.target.checked ? {} : { attachment_ids: [], include_goal: false, include_diagrams: false }) }); })} />{t("Include attachments")}</label>
                  <p className="text-xs muted">{presentation.include_attachments ? t("Selected files will be sent to {destination}.", { destination: projects.find(item => item.id === project)?.name || project }) : t("No file will be sent to the external platform.")}</p>
                  {presentation.include_attachments && <div className="space-y-3">
                    <p className="text-xs muted">{t("Select each file to transfer. Original files and generated goal.md are separate choices.")}</p>
                    {(preview.available_attachments || []).map(file => <div key={file.id}>
                      <label className="flex items-start gap-2 text-sm"><input type="checkbox" disabled={!file.transferable} checked={file.kind === "goal" ? presentation.include_goal : file.kind === "diagrams" ? presentation.include_diagrams : presentation.attachment_ids.includes(file.id)} onChange={event => change(() => { void recompose(file.kind === "goal" ? { include_goal: event.target.checked } : file.kind === "diagrams" ? { include_diagrams: event.target.checked } : { attachment_ids: event.target.checked ? [...presentation.attachment_ids, file.id] : presentation.attachment_ids.filter(id => id !== file.id) }); })} /><span className="min-w-0 break-words">{file.name}<span className="ml-2 text-xs muted">{t(file.kind === "goal" ? "Generated goal.md" : file.kind === "diagrams" ? "Diagram annex (Mermaid)" : "Original attachment")} · {Math.ceil(file.size / 1024)} KB</span></span></label>
                      {!file.transferable && <p className="ml-6 mt-1 text-xs muted">{t(file.reason || "This connector cannot transfer this file.")}</p>}
                    </div>)}
                    {!preview.available_attachments?.length && <p className="text-xs muted">{t("No transferable files are available.")}</p>}
                  </div>}
                </fieldset>
                <h3 className="mt-6">{t("Publication preview")}</h3>
                <p className="mt-2 break-words text-sm font-semibold">{title}</p>
                <p className="mt-1 flex items-center gap-2 text-xs muted"><ProviderLogo provider={connectors.find(item => String(item.id) === connector)?.platform} />{t("Analysis version {number}", { number: version })} · {projects.find(item => item.id === project)?.name || project}</p>
                <div className="markdown-preview mt-3 rounded border bg-muted p-4">
                  {preview.format === "markdown" ? (
                    <SafeMarkdown>
                      {renderedBody}
                    </SafeMarkdown>
                  ) : (
                    <p className="whitespace-pre-wrap">{renderedBody}</p>
                  )}
                </div>
                <p className="my-4 text-xs muted">
                  {t(
                    "Creating this ticket sends the reviewed content to the selected service. No source code will be modified.",
                  )}
                </p>
                <div className="mb-4 text-xs muted" aria-label={t("Attachment transfer preview")}>
                  <p>{t("Files to transfer")}: {presentation.include_attachments ? (preview.selected_attachments || []).map(file => file.name).join(", ") || t("None") : t("None")}</p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Button type="button" variant="outline" disabled={busy} onClick={async () => { setBusy(true); setError(""); try { await saveDraft(); } catch (error) { setError((error as Error).message); } finally { setBusy(false); } }}>{t("Save publication draft")}</Button>
                  <Button type="button" variant="ghost" disabled={busy} onClick={() => change(() => { void reloadDraft(); })}>{t("Reload saved draft")}</Button>
                  {draftSaveFailed && <Button type="button" variant="ghost" disabled={busy} onClick={finishClose}>{t("Close without saving")}</Button>}
                  {saved && !dirty && <p role="status" className="text-xs muted">{t("Publication draft saved.")}</p>}
                <Button
                  disabled={busy || preview.publication_allowed === false || !title.trim() || !fieldBody.trim() || preview.fields.some(field => field.required && !field.read_only && (fields[field.id] === "" || fields[field.id] === undefined || fields[field.id] === null || fields[field.id] === false || (Array.isArray(fields[field.id]) && !(fields[field.id] as unknown[]).length))) || (!!preview.issue_types.length && !issueType) || (presentation.ticket_format === "project" && !!preview.templates.length && !template)}
                >
                  {t("Create ticket")}
                </Button>
                </div>
              </fieldset>
            )}
          </form>
        )}
      </dialog>
    </>
  );
}
