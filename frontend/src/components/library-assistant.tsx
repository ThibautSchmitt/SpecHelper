"use client";

import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  FlaskConical,
  LoaderCircle,
  MessageSquare,
  Save,
  Sparkles,
  XCircle,
} from "lucide-react";
import { AssistantLogo } from "@/components/assistant-logo";
import type { AIConnection } from "@/components/ai-connections";
import type { LibraryDefinition, LibraryDraft } from "@/components/ai-library";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, send, statuses } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { libraryValidationMessage } from "@/lib/library-validation";

type AssistantDraft = {
  id: string;
  kind: "agent" | "skill";
  status: string;
  revision: number;
  connection_id: number;
  definition: LibraryDraft | null;
  messages: { role: string; content: string; questions: string[] }[];
  validation: {
    valid: boolean;
    errors: string[];
    compatibility?: Record<string, boolean>;
  };
  recommendations: {
    kind: string;
    slug: string;
    name: string;
    reason: string;
  }[];
  job: {
    id: number;
    status: string;
    operation: string;
    connection_name: string;
    agent: string;
    model: string;
    public_role: string;
    error: string;
    waiting_reason?: string;
  } | null;
  test_result: {
    summary: string;
    checks: string[];
    limitations: string[];
    revision: number;
  } | null;
  activated_definition: LibraryDefinition | null;
  updated_at: string;
};
const labels: Record<string, string> = {
  DRAFT: "Draft",
  NEEDS_CLARIFICATION: "Needs clarification",
  PROPOSED: "Ready for your review",
  ACTIVE: "Active",
  CANCELLED: "Cancelled",
};
const capLabels: Record<string, string> = {
  read_sources: "Read project sources",
  read_attachments: "Read attachments",
  read_database: "Read the business database",
  structured_output: "Produce structured results",
};
const toggle = (values: string[], value: string) =>
  values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
const canonical = (value: LibraryDraft | null) =>
  value ? JSON.stringify({ ...value, enabled: false }) : "";
function editable(value: LibraryDraft | null): LibraryDraft | null {
  if (!value) return null;
  const text = (entry: unknown) => (typeof entry === "string" ? entry : "");
  const list = (entry: unknown) =>
    Array.isArray(entry)
      ? entry.filter((item) => typeof item === "string")
      : [];
  return {
    ...value,
    slug: text(value.slug),
    name: text(value.name),
    objective: text(value.objective),
    instructions: text(value.instructions),
    enabled: false,
    compatibility: list(value.compatibility),
    required_capabilities: list(value.required_capabilities),
    skills: list(value.skills),
    expected_checks: list(value.expected_checks),
  };
}

function DefinitionComparison({
  before,
  after,
  skills,
}: {
  before: LibraryDraft | null;
  after: LibraryDraft;
  skills: LibraryDefinition[];
}) {
  const { t } = useI18n();
  const fields = [
    ["slug", "Identifier"],
    ["name", "Name"],
    ["objective", "Objective"],
    ["instructions", "Instructions"],
    ["expected_checks", "Expected checks"],
    ["compatibility", "Compatible assistants"],
    ["required_capabilities", "Required capabilities"],
    ["skills", "Required skills"],
  ] as const;
  const changed = fields.filter(
    ([key]) =>
      JSON.stringify(before?.[key] || []) !== JSON.stringify(after[key] || []),
  );
  function display(
    value: LibraryDraft | null,
    key: (typeof fields)[number][0],
  ) {
    if (!value) return t("No previous proposal.");
    const item = value[key];
    if (Array.isArray(item)) {
      if (key === "compatibility" && !item.length)
        return t("All supported assistants");
      return (
        item
          .map((entry) =>
            key === "compatibility"
              ? entry === "codex"
                ? "ChatGPT / Codex"
                : "Claude Code"
              : key === "required_capabilities"
                ? t(capLabels[entry] || entry)
                : key === "skills"
                  ? skills.find((skill) => skill.slug === entry)?.name || entry
                  : entry,
          )
          .join("\n") || t("None")
      );
    }
    return item || t("None");
  }
  return (
    <div className="mt-3 space-y-4">
      {!changed.length && (
        <p className="text-sm muted">
          {t("No changes from the previous proposal.")}
        </p>
      )}
      {changed.map(([key, label]) => (
        <section key={key} className="min-w-0 rounded-md border p-3">
          <h5 className="text-sm font-medium">{t(label)}</h5>
          <div className="mt-3 grid min-w-0 gap-3 sm:grid-cols-2">
            {[
              ["Previous proposal", before],
              ["Current draft", after],
            ].map(([heading, value]) => (
              <div key={heading as string} className="min-w-0">
                <p className="mb-1 text-xs muted">{t(heading as string)}</p>
                <p className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-sm">
                  {display(value as LibraryDraft | null, key)}
                </p>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

export function LibraryAssistant({
  kind,
  onClose,
  onSaved,
}: {
  kind: "agent" | "skill";
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { t, language, dateLocale } = useI18n();
  const [connections, setConnections] = useState<AIConnection[]>([]);
  const [skills, setSkills] = useState<LibraryDefinition[]>([]);
  const [drafts, setDrafts] = useState<AssistantDraft[]>([]);
  const [current, setCurrent] = useState<AssistantDraft | null>(null);
  const [definition, setDefinition] = useState<LibraryDraft | null>(null);
  const [previous, setPrevious] = useState<LibraryDraft | null>(null);
  const [connection, setConnection] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState("");
  const [demo, setDemo] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmActivate, setConfirmActivate] = useState(false);
  const section = useRef<HTMLElement>(null);
  const alive = useRef(true);
  const prefix = `assistant-${kind}`;
  const running =
    !!current?.job && ["QUEUED", "RUNNING"].includes(current.job.status);
  const immutable =
    current?.status === "ACTIVE" || current?.status === "CANCELLED";
  const dirty =
    canonical(definition) !== canonical(current?.definition || null);

  function receive(value: AssistantDraft, preservePrevious = true) {
    if (!alive.current) return;
    if (
      preservePrevious &&
      value.definition &&
      canonical(value.definition) !== canonical(current?.definition || null)
    )
      setPrevious(current?.definition || null);
    setCurrent(value);
    setDefinition(editable(value.definition));
    setConfirmActivate(false);
    setDrafts((values) => [
      value,
      ...values.filter((item) => item.id !== value.id),
    ]);
  }
  useEffect(() => {
    alive.current = true;
    Promise.all([
      api<AIConnection[]>("/ai-connections"),
      api<LibraryDefinition[]>("/library/skill"),
      api<AssistantDraft[]>("/library-assistant/drafts"),
    ])
      .then(async ([available, required, saved]) => {
        if (!alive.current) return;
        setConnections(available);
        setSkills(required);
        setDrafts(saved.filter((item) => item.kind === kind));
        setConnection(
          String(
            available.find(
              (item) => item.enabled && item.status === "CONNECTED",
            )?.id || "",
          ),
        );
        const resume = new URLSearchParams(window.location.search).get(
          "library_draft",
        );
        let found = saved.find(
          (item) => item.id === resume && item.kind === kind,
        );
        if (!found && resume) {
          const loaded = await api<AssistantDraft>(
            `/library-assistant/drafts/${encodeURIComponent(resume)}`,
          );
          if (!alive.current) return;
          if (loaded.kind === kind) found = loaded;
        }
        if (found) {
          setCurrent(found);
          setDefinition(editable(found.definition));
          setConnection(String(found.connection_id));
        }
      })
      .catch((value) => {
        if (alive.current) setError(value.message);
      })
      .finally(() => {
        if (alive.current) setLoading(false);
      });
    section.current?.focus();
    return () => {
      alive.current = false;
    };
  }, [kind]);
  useEffect(() => {
    if (!running || !current) return;
    let stopped = false;
    const timer = setInterval(() => {
      api<AssistantDraft>(`/library-assistant/drafts/${current.id}`)
        .then((value) => {
          if (!stopped) {
            receive(value);
            setError("");
          }
        })
        .catch((value) => {
          if (!stopped) setError(value.message);
        });
    }, 2000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [current?.id, running]);

  async function action(task: () => Promise<AssistantDraft>, success = "") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const value = await task();
      receive(value);
      if (alive.current) setNotice(success);
    } catch (value) {
      if (alive.current) setError((value as Error).message);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  function edit(next: LibraryDraft) {
    setDefinition({ ...next, enabled: false });
    setConfirmActivate(false);
    setNotice("");
  }
  const canActivate =
    !!definition &&
    !!current?.validation.valid &&
    !dirty &&
    !busy &&
    !running &&
    !immutable;
  const existing = drafts.filter(
    (item) =>
      item.kind === kind && !["ACTIVE", "CANCELLED"].includes(item.status),
  );
  return (
    <section
      ref={section}
      tabIndex={-1}
      className="min-w-0 rounded-xl border bg-muted/20 p-4 sm:p-5 space-y-5 outline-none"
      aria-label={t("Creation assistant")}
    >
      <div className="flex flex-wrap justify-between items-start gap-3">
        <div>
          <h3 className="flex items-center gap-2">
            <Sparkles size={18} aria-hidden="true" />
            {t(kind === "agent" ? "Generate an agent" : "Generate a skill")}
          </h3>
          <p className="mt-2 text-sm muted">
            {t(
              "Describe the mission in your own words. The assistant asks only what is needed and prepares an inactive draft for your review.",
            )}
          </p>
        </div>
        <Button variant="ghost" size="sm" disabled={busy} onClick={onClose}>
          {t("Close")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="rounded-md border p-3 text-sm break-words">
          {t(error)}
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm">
          {t(notice)}
        </p>
      )}
      {loading ? (
        <p role="status" className="text-sm muted">
          {t("Loading creation assistant…")}
        </p>
      ) : (
        <>
          {!current && existing.length > 0 && (
            <div className="field">
              <label htmlFor={`${prefix}-resume`}>
                {t("Resume a saved draft")}
              </label>
              <select
                id={`${prefix}-resume`}
                value=""
                onChange={(event) => {
                  const value = drafts.find(
                    (item) => item.id === event.target.value,
                  );
                  if (value) receive(value, false);
                }}
              >
                <option value="">{t("Start a new discussion")}</option>
                {existing.map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.definition?.name || t("Untitled draft")} ·{" "}
                    {new Date(item.updated_at).toLocaleString(dateLocale)}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="grid min-w-0 gap-5 xl:grid-cols-2">
            <section
              className="min-w-0 space-y-4"
              aria-label={t("Clarification discussion")}
            >
              <h4 className="flex items-center gap-2 font-medium">
                <MessageSquare size={16} aria-hidden="true" />
                {t("Clarification discussion")}
              </h4>
              {!current ? (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    action(() =>
                      send("/library-assistant/drafts", {
                        kind,
                        connection_id: Number(connection),
                        language,
                        description,
                      }),
                    );
                  }}
                >
                  <fieldset disabled={busy} className="min-w-0 space-y-4">
                    <div className="field">
                      <label htmlFor={`${prefix}-connection`}>
                        {t("AI connection")}
                      </label>
                      <select
                        id={`${prefix}-connection`}
                        required
                        value={connection}
                        onChange={(event) => setConnection(event.target.value)}
                      >
                        <option value="">{t("Choose an AI connection")}</option>
                        {connections
                          .filter((item) => item.enabled)
                          .map((item) => (
                            <option
                              key={item.id}
                              value={item.id}
                              disabled={item.status !== "CONNECTED"}
                            >
                              {item.name || item.agent} ·{" "}
                              {item.model || t("Provider default model")} ·{" "}
                              {t(
                                statuses[item.availability] ||
                                  statuses[item.status] ||
                                  item.status,
                              )}
                            </option>
                          ))}
                      </select>
                    </div>
                    <div className="field">
                      <label htmlFor={`${prefix}-description`}>
                        {t("What should this definition help with?")}
                      </label>
                      <textarea
                        id={`${prefix}-description`}
                        required
                        maxLength={8000}
                        rows={7}
                        className="w-full rounded-md border bg-background p-3 text-sm"
                        value={description}
                        onChange={(event) => setDescription(event.target.value)}
                      />
                      <p className="mt-2 text-xs muted">
                        {t(
                          "Include the mission, expected inputs and outputs, project context and constraints when useful. Do not include credentials.",
                        )}
                      </p>
                    </div>
                    <Button
                      disabled={!description.trim() || !connection || busy}
                    >
                      <Sparkles size={16} aria-hidden="true" />
                      {t("Start generation")}
                    </Button>
                  </fieldset>
                </form>
              ) : (
                <>
                  <p className="text-xs muted">
                    {t("Draft revision {revision}", {
                      revision: current.revision,
                    })}{" "}
                    · {t(labels[current.status] || current.status)}
                  </p>
                  <ol className="space-y-3" aria-label={t("Creation messages")}>
                    {current.messages.map((item, index) => (
                      <li
                        key={index}
                        className="rounded-lg border bg-background p-3"
                      >
                        <p className="mb-2 text-xs font-medium muted">
                          {t(item.role === "user" ? "You" : "Assistant")}
                        </p>
                        <p className="whitespace-pre-wrap break-words text-sm">
                          {item.content}
                        </p>
                        {item.questions?.length > 0 && (
                          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm">
                            {item.questions.map((question, q) => (
                              <li key={q}>{question}</li>
                            ))}
                          </ul>
                        )}
                      </li>
                    ))}
                  </ol>
                  {current.recommendations.length > 0 && (
                    <div className="rounded-lg border p-3 space-y-2">
                      <h4 className="text-sm font-medium">
                        {t("Existing definitions to consider")}
                      </h4>
                      {current.recommendations.map((item) => (
                        <p
                          key={`${item.kind}-${item.slug}`}
                          className="text-sm break-words"
                        >
                          <strong>{item.name}</strong> · {item.slug}
                          <br />
                          {item.reason}
                        </p>
                      ))}
                    </div>
                  )}
                  {current.job && (
                    <div
                      role="status"
                      className="rounded-lg border bg-background p-3 text-sm space-y-2"
                      aria-label={t("Assistant task")}
                    >
                      <div className="flex items-center gap-2">
                        {running ? (
                          <LoaderCircle
                            className="animate-spin"
                            size={16}
                            aria-hidden="true"
                          />
                        ) : current.job.status === "ERROR" ? (
                          <XCircle size={16} aria-hidden="true" />
                        ) : (
                          <CheckCircle2 size={16} aria-hidden="true" />
                        )}
                        <strong>
                          #{current.job.id} ·{" "}
                          {t(
                            statuses[current.job.status] || current.job.status,
                          )}
                        </strong>
                      </div>
                      <p className="flex flex-wrap items-center gap-2">
                        <AssistantLogo agent={current.job.agent} />
                        {current.job.connection_name} ·{" "}
                        {current.job.model || t("Provider default model")}
                      </p>
                      <p>
                        {t(
                          current.job.public_role === "library_test"
                            ? "Definition sandbox test"
                            : "Definition generator",
                        )}
                      </p>
                      {current.job.error && <p>{t(current.job.error)}</p>}
                      {current.job.waiting_reason && (
                        <p>{t(current.job.waiting_reason)}</p>
                      )}
                      <p className="text-xs muted">
                        {t(
                          "This task uses the shared queue. You can close this panel and resume later.",
                        )}
                      </p>
                    </div>
                  )}
                  {!immutable && (
                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        action(async () => {
                          const value = await send<AssistantDraft>(
                            `/library-assistant/drafts/${current.id}/messages`,
                            { expected_revision: current.revision, message },
                          );
                          setMessage("");
                          return value;
                        });
                      }}
                    >
                      <div className="field">
                        <label htmlFor={`${prefix}-message`}>
                          {t("Answer or request a revision")}
                        </label>
                        <textarea
                          id={`${prefix}-message`}
                          required
                          rows={3}
                          maxLength={8000}
                          className="w-full rounded-md border bg-background p-3 text-sm"
                          value={message}
                          disabled={busy || running}
                          onChange={(event) => setMessage(event.target.value)}
                        />
                      </div>
                      <Button
                        className="mt-3"
                        variant="outline"
                        disabled={busy || running || dirty || !message.trim()}
                      >
                        {t("Revise")}
                      </Button>
                      {dirty && (
                        <p className="mt-2 text-xs muted">
                          {t(
                            "Save your edits before continuing the discussion or testing.",
                          )}
                        </p>
                      )}
                    </form>
                  )}
                </>
              )}
            </section>
            <section
              className="min-w-0 space-y-4"
              aria-label={t("Structured draft")}
            >
              <h4 className="font-medium">{t("Structured draft")}</h4>
              {!definition ? (
                <p className="rounded-lg border border-dashed p-5 text-sm muted">
                  {t(
                    "Your editable proposal and configuration checks will appear here after clarification.",
                  )}
                </p>
              ) : (
                <>
                  <fieldset
                    disabled={busy || running || immutable}
                    className="min-w-0 space-y-3"
                  >
                    <div className="field">
                      <label htmlFor={`${prefix}-slug`}>
                        {t("Identifier")}
                      </label>
                      <Input
                        id={`${prefix}-slug`}
                        value={definition.slug}
                        maxLength={50}
                        onChange={(event) =>
                          edit({ ...definition, slug: event.target.value })
                        }
                      />
                    </div>
                    <div className="field">
                      <label htmlFor={`${prefix}-name`}>{t("Name")}</label>
                      <Input
                        id={`${prefix}-name`}
                        value={definition.name}
                        maxLength={100}
                        onChange={(event) =>
                          edit({ ...definition, name: event.target.value })
                        }
                      />
                    </div>
                    <div className="field">
                      <label htmlFor={`${prefix}-objective`}>
                        {t("Objective")}
                      </label>
                      <textarea
                        id={`${prefix}-objective`}
                        className="w-full rounded-md border bg-background p-3 text-sm"
                        rows={3}
                        maxLength={4000}
                        value={definition.objective}
                        onChange={(event) =>
                          edit({ ...definition, objective: event.target.value })
                        }
                      />
                    </div>
                    <div className="field">
                      <label htmlFor={`${prefix}-instructions`}>
                        {t("Instructions")}
                      </label>
                      <textarea
                        id={`${prefix}-instructions`}
                        className="w-full rounded-md border bg-background p-3 text-sm"
                        rows={8}
                        maxLength={12000}
                        value={definition.instructions}
                        onChange={(event) =>
                          edit({
                            ...definition,
                            instructions: event.target.value,
                          })
                        }
                      />
                    </div>
                    <div className="field">
                      <label htmlFor={`${prefix}-checks`}>
                        {t("Expected checks")}
                      </label>
                      <textarea
                        id={`${prefix}-checks`}
                        className="w-full rounded-md border bg-background p-3 text-sm"
                        rows={3}
                        maxLength={12000}
                        value={(definition.expected_checks || []).join("\n")}
                        onChange={(event) =>
                          edit({
                            ...definition,
                            expected_checks: event.target.value.split("\n"),
                          })
                        }
                      />
                      <p className="mt-1 text-xs muted">
                        {t("One check per line.")}
                      </p>
                    </div>
                    <fieldset className="min-w-0 space-y-2">
                      <legend className="mb-2 text-sm font-medium">
                        {t("Compatible assistants")}
                      </legend>
                      <p className="text-xs muted">
                        {t(
                          "Leave both unchecked for all supported assistants.",
                        )}
                      </p>
                      <div className="flex flex-wrap gap-4">
                        {[
                          ["codex", "ChatGPT / Codex"],
                          ["claude", "Claude Code"],
                        ].map(([value, label]) => (
                          <label key={value} className="flex gap-2 text-sm">
                            <input
                              type="checkbox"
                              checked={definition.compatibility.includes(value)}
                              onChange={() =>
                                edit({
                                  ...definition,
                                  compatibility: toggle(
                                    definition.compatibility,
                                    value,
                                  ),
                                })
                              }
                            />
                            {label}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <fieldset className="min-w-0 space-y-2">
                      <legend className="mb-2 text-sm font-medium">
                        {t("Required capabilities")}
                      </legend>
                      <p className="text-xs muted">
                        {t(
                          "Requirements check compatibility; they do not grant permissions.",
                        )}
                      </p>
                      {Object.entries(capLabels).map(([value, label]) => (
                        <label key={value} className="flex gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={definition.required_capabilities.includes(
                              value,
                            )}
                            onChange={() =>
                              edit({
                                ...definition,
                                required_capabilities: toggle(
                                  definition.required_capabilities,
                                  value,
                                ),
                              })
                            }
                          />
                          {t(label)}
                        </label>
                      ))}
                    </fieldset>
                    {kind === "agent" && (
                      <fieldset className="min-w-0 space-y-2">
                        <legend className="mb-2 text-sm font-medium">
                          {t("Required skills")}
                        </legend>
                        {skills
                          .filter(
                            (item) =>
                              item.enabled ||
                              definition.skills?.includes(item.slug),
                          )
                          .map((item) => (
                            <label
                              key={item.slug}
                              className="flex gap-2 text-sm"
                            >
                              <input
                                type="checkbox"
                                checked={
                                  definition.skills?.includes(item.slug) ||
                                  false
                                }
                                onChange={() =>
                                  edit({
                                    ...definition,
                                    skills: toggle(
                                      definition.skills || [],
                                      item.slug,
                                    ),
                                  })
                                }
                              />
                              {item.name}
                              {!item.enabled && ` · ${t("Inactive")}`}
                            </label>
                          ))}
                      </fieldset>
                    )}
                  </fieldset>
                  <div
                    role="status"
                    className="rounded-lg border p-3 text-sm"
                    aria-label={t("Configuration checks")}
                  >
                    <p className="font-medium">
                      {t(
                        dirty
                          ? "Save changes to run configuration checks."
                          : current?.validation.valid
                            ? "Configuration checks passed."
                            : "Configuration needs changes.",
                      )}
                    </p>
                    {!dirty &&
                      current?.validation.errors.map((value, index) => (
                        <p key={index} className="mt-2 break-words">
                          {libraryValidationMessage(value, t)}
                        </p>
                      ))}
                    {!dirty && current?.validation.valid && (
                      <div className="mt-2 space-y-1">
                        {Object.entries(
                          current.validation.compatibility || {},
                        ).map(([provider, compatible]) => (
                          <p key={provider}>
                            {provider === "codex"
                              ? "ChatGPT / Codex"
                              : "Claude Code"}{" "}
                            · {t(compatible ? "Compatible" : "Not compatible")}
                          </p>
                        ))}
                      </div>
                    )}
                    <p className="mt-2 text-xs muted">
                      {t(
                        "Instructions cannot grant access to secrets, other environments, arbitrary networks or write operations.",
                      )}
                    </p>
                  </div>
                  <details className="rounded-lg border p-3">
                    <summary className="cursor-pointer text-sm font-medium">
                      {t("Review changes")}
                    </summary>
                    <p className="mt-2 text-xs muted">
                      {t(
                        "Compare the previous proposal with the current draft before activation.",
                      )}
                    </p>
                    <DefinitionComparison
                      before={
                        previous || (dirty ? current?.definition || null : null)
                      }
                      after={definition}
                      skills={skills}
                    />
                  </details>
                  {!immutable && current && (
                    <>
                      <Button
                        variant="outline"
                        disabled={busy || running}
                        onClick={() =>
                          action(
                            () =>
                              send(
                                `/library-assistant/drafts/${current.id}`,
                                {
                                  expected_revision: current.revision,
                                  definition: {
                                    ...definition,
                                    enabled: false,
                                    expected_checks: (
                                      definition.expected_checks || []
                                    )
                                      .map((value) => value.trim())
                                      .filter(Boolean),
                                  },
                                },
                                "PUT",
                              ),
                            "Draft saved. It remains inactive.",
                          )
                        }
                      >
                        <Save size={16} aria-hidden="true" />
                        {t("Save as draft")}
                      </Button>
                      <div className="rounded-lg border p-3 space-y-3">
                        <label
                          htmlFor={`${prefix}-demo`}
                          className="text-sm font-medium"
                        >
                          {t("Demonstration request")}
                        </label>
                        <textarea
                          id={`${prefix}-demo`}
                          className="w-full rounded-md border bg-background p-3 text-sm"
                          rows={3}
                          maxLength={8000}
                          value={demo}
                          disabled={busy || running}
                          onChange={(event) => setDemo(event.target.value)}
                        />
                        <p className="text-xs muted">
                          {t(
                            "The test uses a temporary session with the saved draft. It does not change repositories or business databases.",
                          )}
                        </p>
                        <Button
                          variant="outline"
                          disabled={
                            busy ||
                            running ||
                            dirty ||
                            !current.validation.valid ||
                            !demo.trim()
                          }
                          onClick={() =>
                            action(
                              () =>
                                send(
                                  `/library-assistant/drafts/${current.id}/test`,
                                  { expected_revision: current.revision, demo },
                                ),
                              "Sandbox test added to the shared queue.",
                            )
                          }
                        >
                          <FlaskConical size={16} aria-hidden="true" />
                          {t("Test in a sandbox")}
                        </Button>
                      </div>
                    </>
                  )}
                  {current?.test_result && (
                    <section
                      className="rounded-lg border p-3 space-y-2"
                      aria-label={t("Sandbox test result")}
                    >
                      <h4 className="font-medium text-sm">
                        {t("Sandbox test result")}
                      </h4>
                      <p className="whitespace-pre-wrap break-words text-sm">
                        {current.test_result.summary}
                      </p>
                      {current.test_result.checks.map((value, index) => (
                        <p key={index} className="text-sm break-words">
                          {value}
                        </p>
                      ))}
                      {current.test_result.limitations.map((value, index) => (
                        <p key={index} className="text-sm muted break-words">
                          {value}
                        </p>
                      ))}
                      <p className="text-xs muted">
                        {t("Tested draft revision {revision}", {
                          revision: current.test_result.revision,
                        })}
                      </p>
                    </section>
                  )}
                  {!immutable && current && (
                    <div className="space-y-3">
                      <Button
                        disabled={!canActivate}
                        onClick={() => setConfirmActivate(true)}
                      >
                        {t("Activate")}
                      </Button>
                      <p className="text-xs muted">
                        {t(
                          "Activation creates an immutable library version after your explicit approval. Generation and testing never activate a definition.",
                        )}
                      </p>
                      {confirmActivate && (
                        <div
                          role="group"
                          aria-label={t("Confirm activation")}
                          className="rounded-lg border bg-background p-3 space-y-3"
                        >
                          <p className="text-sm">
                            {t("Activate {name} in the shared library?", {
                              name: definition.name,
                            })}
                          </p>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              disabled={!canActivate}
                              onClick={() =>
                                action(async () => {
                                  const value = await send<AssistantDraft>(
                                    `/library-assistant/drafts/${current.id}/activate`,
                                    { expected_revision: current.revision },
                                  );
                                  await onSaved();
                                  return value;
                                }, "Definition activated in the shared library.")
                              }
                            >
                              {t("Confirm activation")}
                            </Button>
                            <Button
                              variant="outline"
                              disabled={busy}
                              onClick={() => setConfirmActivate(false)}
                            >
                              {t("Cancel")}
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </section>
          </div>
          {current && !immutable && (
            <div className="border-t pt-4 flex flex-wrap gap-3">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() =>
                  action(
                    () =>
                      send(`/library-assistant/drafts/${current.id}/cancel`, {
                        expected_revision: current.revision,
                      }),
                    "Creation cancelled. No definition was activated.",
                  )
                }
              >
                {t("Cancel creation")}
              </Button>
              <Button variant="ghost" disabled={busy} onClick={onClose}>
                {t("Close and resume later")}
              </Button>
            </div>
          )}
          {immutable && (
            <Button
              variant="outline"
              onClick={() => {
                setCurrent(null);
                setDefinition(null);
                setPrevious(null);
                setDescription("");
                setMessage("");
                setDemo("");
                setNotice("");
              }}
            >
              {t("Start a new discussion")}
            </Button>
          )}
        </>
      )}
    </section>
  );
}
