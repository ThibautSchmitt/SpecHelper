"use client";
import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
type Preview = {
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
};
type Payload = {
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
    api<TicketConnector[]>("/ticket-connectors")
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
  useEffect(() => {
    if (!open || !connector || !project) return;
    let alive = true;
    setBusy(true);
    setError("");
    setPreview(null);
    send<Preview>(`${endpoint}/publication-preview`, {
      connector_id: Number(connector),
      project,
      template_id: template,
      issue_type: issueType,
    })
      .then((v) => {
        if (alive) {
          setPreview(v);
          setTitle(v.title);
          setBody(v.body);
          setFields({
            ...Object.fromEntries(
              v.fields.map((f) => [
                f.id,
                f.default ?? (f.type === "checkboxes" ? [] : ""),
              ]),
            ),
            ...v.values,
          });
          setLabels(v.defaults?.labels || []);
          setAssignees(v.defaults?.assignees || []);
          setDirty(false);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
    };
  }, [open, connector, project, template, issueType, endpoint]);
  const renderedBody = preview?.render_fields
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
      const response = await fetch(`/api${endpoint}/publications`, {
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
  function close() {
    dialog.current?.close();
    setOpen(false);
    setPreview(null);
    setResult(null);
    setDirty(false);
    setConnector("");
    setPending(null);
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
        {t("Publish ticket")}
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
            onSubmit={(event) => {
              event.preventDefault();
              if (!preview) return;
              publish({
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
              {!!preview?.templates.length && (
                <div className="field">
                  <label htmlFor="publish-template">
                    {t("Ticket template")}
                  </label>
                  <select
                    id="publish-template"
                    value={template}
                    onChange={(e) => change(() => setTemplate(e.target.value))}
                  >
                    <option value="">{t("Default format")}</option>
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
                    onChange={(e) => change(() => setIssueType(e.target.value))}
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
                  const current = project;
                  setProject("");
                  setTimeout(() => setProject(current), 0);
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
                <h3 className="mt-6">{t("Publication preview")}</h3>
                <div className="markdown-preview mt-3 rounded border bg-muted p-4">
                  {preview.format === "markdown" ? (
                    <Markdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: (props) => (
                          <a
                            {...props}
                            target="_blank"
                            rel="noopener noreferrer"
                          />
                        ),
                      }}
                    >
                      {renderedBody}
                    </Markdown>
                  ) : (
                    <p className="whitespace-pre-wrap">{renderedBody}</p>
                  )}
                </div>
                <p className="my-4 text-xs muted">
                  {t(
                    "Creating this ticket sends the reviewed content to the selected service. No source code will be modified.",
                  )}
                </p>
                <Button
                  disabled={busy || !title.trim() || !renderedBody.trim()}
                >
                  {t("Create ticket")}
                </Button>
              </fieldset>
            )}
          </form>
        )}
      </dialog>
    </>
  );
}
