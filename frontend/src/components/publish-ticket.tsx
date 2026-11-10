"use client";
import { useEffect, useId, useImperativeHandle, useRef, useState, type ReactNode, type Ref } from "react";
import { ProviderLogo } from "@/components/provider-logo";
import { MarkdownReader } from "@/components/markdown-reader";
import { secureFetch } from "@/lib/access";
import { api, send } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useTicketUrlResolver } from "@/lib/ticket-links";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  publicationPlatforms,
  type TicketConnector,
  type Destination,
} from "@/components/ticket-connectors";

type Option = { id: string; name: string };
function CompactOptions({label,options,value,onChange,single=false}:{label:string;options:Option[];value:string[];onChange:(value:string[])=>void;single?:boolean}) {
  const {t}=useI18n();
  const [query,setQuery]=useState("");
  return <details className="rounded-md border p-2 text-sm">
    <summary className="cursor-pointer">{label}<span className="muted"> · {value.length?options.filter(item=>value.includes(item.id)).map(item=>item.name).join(", "):t("Optional")}</span></summary>
    <div className="mt-2 space-y-2">
      <Input aria-label={t("Search {label}",{label})} placeholder={t("Search…")} value={query} onChange={event=>setQuery(event.target.value)}/>
      <div className="max-h-36 space-y-2 overflow-y-auto" role="group" aria-label={label}>{options.filter(item=>item.name.toLocaleLowerCase().includes(query.toLocaleLowerCase())).map(item=><label key={item.id} className="flex items-center gap-2">
        <input type="checkbox" checked={value.includes(item.id)} onChange={event=>onChange(event.target.checked?(single?[item.id]:[...value,item.id]):value.filter(id=>id!==item.id))}/>{item.name}
      </label>)}</div>
    </div>
  </details>;
}
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
  document_attachment_policy?:{enabled:boolean;max_bytes:number;extensions?:string[]};
  draft_id?: string;
  draft_revision?: number;
  template_id?: string;
  issue_type?: string;
  fallback_reason?: string;
  publication_allowed?: boolean;
  requires_unverified_confirmation?: boolean;
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
  document_generations?:Record<string,number>;
  conversation_ticket_id?: string;
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
  unverified_confirmed?: boolean;
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

function recoveryPayload(attempt:Attempt):Payload {
  const allowed=["conversation_ticket_id","title","body","fields","labels","assignees","template_id","issue_type","options_revision","ticket_format","include_business_analysis","include_technical_analysis","include_attachments","attachment_ids","include_goal","include_diagrams","unverified_confirmed","document_generations"];
  const snapshot=Object.fromEntries(Object.entries(attempt.snapshot).filter(([key])=>allowed.includes(key)));
  return {...snapshot,connector_id:attempt.connector_id,project:attempt.project,idempotency_key:attempt.idempotency_key,confirmed:true} as Payload;
}

function remember(key: string, payload: Payload | null) {
  try {
    if (payload) sessionStorage.setItem(key, JSON.stringify(payload));
    else sessionStorage.removeItem(key);
  } catch {}
}

export type PublicationControls = {
  save:(content:{title:string;body:string})=>Promise<void>;
  close:()=>Promise<void>;
};

export function PublishTicket({
  requestId,
  version,
  triggerLabel = "Prepare ticket",
  preparedDraft,
  conversationTicketId,
  onClosed,
  onAnalyze,
  embedded = false,
  onPublished,
  preparedSource = false,
  autoOpen = false,
  hideTrigger = false,
  documents = [],
  unified = false, controller, beforeSave, footerActions, advancedContent,
  disabled = false, hideFooter = false,
  onDocumentsChange, onLockedChange, onDirtyChange,
}: {
  requestId: string;
  version: number | null;
  triggerLabel?: string;
  preparedDraft?: { title: string; body: string };
  conversationTicketId?: string;
  onClosed?: () => void;
  onAnalyze?: () => void;
  embedded?: boolean;
  onPublished?: () => void;
  preparedSource?: boolean;
  autoOpen?: boolean;
  hideTrigger?: boolean;
  documents?:string[];
  unified?:boolean;
  controller?:Ref<PublicationControls>;
  beforeSave?:()=>Promise<{title:string;body:string}>;
  footerActions?:ReactNode;
  advancedContent?:ReactNode;
  disabled?:boolean;
  hideFooter?:boolean;
  onDocumentsChange?:(documents:string[])=>void;
  onLockedChange?:(locked:boolean)=>void;
  onDirtyChange?:(dirty:boolean)=>void;
}) {
  const { t } = useI18n();
  const ticketUrl = useTicketUrlResolver();
  const dialog = useRef<HTMLDialogElement>(null);
  const prefix = useId();
  const [open, setOpen] = useState(autoOpen);
  const [confirmation, setConfirmation] = useState<Payload | null>(null);
  const confirmationPanel = useRef<HTMLDivElement>(null);
  useEffect(()=>{if(confirmation){confirmationPanel.current?.focus();confirmationPanel.current?.scrollIntoView({block:"nearest"});}},[confirmation]);
  useEffect(()=>{if(autoOpen&&!embedded)dialog.current?.showModal();},[autoOpen,embedded]);
  const [connectors, setConnectors] = useState<TicketConnector[]>([]);
  const [connector, setConnector] = useState("");
  const [projects, setProjects] = useState<Destination[]>([]);
  const [project, setProject] = useState("");
  const [template, setTemplate] = useState("");
  const [issueType, setIssueType] = useState("");
  const [presentation, setPresentation] = useState<Presentation>(defaultPresentation);
  const previewGeneration = useRef(0);
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
  const [selectedDocuments,setSelectedDocuments]=useState(documents);
  const [generatingDocuments,setGeneratingDocuments]=useState(false);
  const [documentError,setDocumentError]=useState(false);
  const [writers,setWriters]=useState<{connection_id:number;name:string;model:string}[]>([]);
  const [writer,setWriter]=useState("");
  const documentGeneration=useRef(0);
  useEffect(()=>()=>{documentGeneration.current++;},[]);
  const [result, setResult] = useState<Publication | null>(null);
  const [pending, setPending] = useState<Payload | null>(null);
  useEffect(()=>{onLockedChange?.(generatingDocuments||!!confirmation||busy&&!!pending);},[generatingDocuments,confirmation,busy,pending,onLockedChange]);
  useEffect(()=>{onDirtyChange?.(dirty);},[dirty,onDirtyChange]);
  useEffect(()=>{if(unified&&preparedDraft){setTitle(preparedDraft.title);setBody(preparedDraft.body);}},[unified,preparedDraft?.title,preparedDraft?.body]);
  useEffect(()=>{if(unified)setSelectedDocuments(documents);},[unified,documents.join(",")]);
  useImperativeHandle(controller,()=>({save:async content=>{if(preview)await saveDraft(content);},close}));
  const storageKey = `publication:${requestId}:${version}${conversationTicketId ? ":"+conversationTicketId : ""}`;
  const endpoint = preparedSource && conversationTicketId ? `/analyses/${requestId}/tickets/${conversationTicketId}` : `/requests/${requestId}/versions/${version}`;
  const ticketQuery = conversationTicketId ? `&conversation_ticket_id=${conversationTicketId}` : "";
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
    api<Attempt[]>(`${endpoint}/publications${conversationTicketId ? "?conversation_ticket_id="+conversationTicketId : ""}`)
      .then((attempts) => {
        if (!alive) return;
        const unfinished = attempts.find((p) =>
          ["UNCERTAIN", "PUBLISHING"].includes(p.status),
        );
        if (unfinished) {
          const payload = recoveryPayload(unfinished);
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
          setConnectors(v);
          setConnector("");
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
          const allowed = v.filter((p) => !current?.projects.length || current.projects.includes(p.id));
          setProjects(allowed);
          setProject(
            allowed.find((p) => p.id === current?.default_project)?.id ||
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
    setTitle(unified&&preparedDraft ? preparedDraft.title : value.title);
    setBody(unified&&preparedDraft ? preparedDraft.body : value.body);
    setTemplate(value.template_id || "");
    setIssueType(value.issue_type || "");
    setPresentation({ ...defaultPresentation, ...Object.fromEntries(Object.keys(defaultPresentation).filter(key => key in value).map(key => [key, value[key as keyof Preview]])) });
    setFields({ ...Object.fromEntries(value.fields.map(field => [field.id, field.default ?? (field.type === "checkboxes" ? [] : "")])), ...value.values });
    setLabels(value.defaults?.labels || []);
    setAssignees(value.defaults?.assignees || []);
    setDirty(false);
    setDraftSaveFailed(false);
  }
  useEffect(() => {
    if (!open || !connector || !project) return;
    const generation = ++previewGeneration.current;
    setBusy(true);
    setError("");
    setPreview(null);
    api<Preview>(`${endpoint}/publication-draft?connector_id=${connector}&project=${encodeURIComponent(project)}${ticketQuery}`)
      .then(async value => {
        if(unified&&value.ticket_format==="project"&&!value.template_id){
          value=await send<Preview>(`${endpoint}/publication-preview`,{conversation_ticket_id:conversationTicketId,connector_id:Number(connector),project,ticket_format:"standard",issue_type:value.issue_type||""});
        }
        if (generation === previewGeneration.current) applyPreview(value);
      })
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
      const value = await send<Preview>(`${endpoint}/publication-preview`, { conversation_ticket_id:conversationTicketId, connector_id: Number(connector), project, template_id: template, issue_type: issueType, ...presentation, ...changes });
      if (generation === previewGeneration.current) applyPreview(value);
    } catch (error) {
      if (generation === previewGeneration.current) { setPresentation(before); setTemplate(previousTemplate); setIssueType(previousType); setError((error as Error).message); }
    } finally {
      if (generation === previewGeneration.current) setBusy(false);
    }
  }
  function draftPayload() {
    return { conversation_ticket_id:conversationTicketId, connector_id: Number(connector), project, title, body, fields, labels, assignees, template_id: template, issue_type: issueType, options_revision: preview?.revision, draft_id: preview?.draft_id, draft_revision: preview?.draft_revision, ...presentation };
  }
  async function saveDraft(content?:{title:string;body:string}) {
    try {
      const value = await send<Preview>(`${endpoint}/publication-draft?connector_id=${connector}&project=${encodeURIComponent(project)}${ticketQuery}`, {...draftPayload(),...(content?{title:content.title,body:content.body}:{})}, "PUT");
      setPreview(value);
      setDirty(false);
      setDraftSaveFailed(false);
      return value;
    } catch (error) {
      setDraftSaveFailed(true);
      throw error;
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
  // Correlation stays in the publication metadata/provider payload, outside the reading view.
  const renderedBody = (referencePattern ? fieldBody.replace(referencePattern, "") : fieldBody)
    .replace(/^\s*spechelper:[0-9a-f-]{36}\s*$/gmi, "").trim();
  const shortPreview = renderedBody.split(/\n\s*\n/).slice(0,2).join("\n\n").slice(0,360);
  const publicationIssues = preview ? [
    ...(selectedDocuments.length && (preview.document_attachment_policy?.enabled === false || preview.document_attachment_policy?.extensions && !preview.document_attachment_policy.extensions.includes("md")) ? [t("This destination cannot receive generated documents. Deselect them to publish without files.")] : []),
    ...(preview.publication_allowed === false
      ? (preview.publication_blockers?.length ? preview.publication_blockers : ["Required independent checks are incomplete. Publication is blocked."]).map(reason => t(reason))
      : []),
    ...(!title.trim() ? [t("Enter a ticket title before creating the ticket.")] : []),
    ...(!fieldBody.trim() ? [t("Enter a ticket description before creating the ticket.")] : []),
    ...preview.fields.filter(field => field.required && !field.read_only && (fields[field.id] === "" || fields[field.id] === undefined || fields[field.id] === null || fields[field.id] === false || (Array.isArray(fields[field.id]) && !(fields[field.id] as unknown[]).length)))
      .map(field => t("Complete the required field: {field}.", { field: field.label })),
    ...(preview.issue_types.length && !issueType ? [t("Select an issue type before creating the ticket.")] : []),
    ...(presentation.ticket_format === "project" && preview.templates.length && !template ? [t("Select a ticket template before creating the ticket.")] : []),
  ] : [];
  const availableFiles=(preview?.available_attachments||[]).filter(file=>!preparedSource||file.kind==="original");
  async function prepareAndConfirm(payload:Payload) {
    if(!conversationTicketId||!selectedDocuments.length){setConfirmation(payload);return;}
    const token=++documentGeneration.current;
    setBusy(true);setGeneratingDocuments(true);setDocumentError(false);setError("");
    try {
      type Documents={generation_id?:number;status:string;error?:string;documents:Record<string,{generation_id:number}>};
      let result=await send<Documents>(`${endpoint}/documents/generate`,{draft_id:payload.draft_id,draft_revision:payload.draft_revision,documents:selectedDocuments,connection_id:writer?Number(writer):undefined});
      while(token===documentGeneration.current&&["QUEUED","RUNNING"].includes(result.status)){
        await new Promise(resolve=>setTimeout(resolve,1500));
        if(token!==documentGeneration.current)return;
        result=await api<Documents>(`${endpoint}/documents/${result.generation_id}`);
      }
      if(token!==documentGeneration.current)return;
      if(result.status!=="DONE" || selectedDocuments.some(kind=>!result.documents?.[kind]))throw new Error(result.error||"Document generation failed. No ticket was sent. Retry or deselect the affected documents.");
      const document_generations=Object.fromEntries(selectedDocuments.map(kind=>[kind,result.documents[kind].generation_id]));
      const {idempotency_key:_,confirmed:__,unverified_confirmed:___,...prepared}=payload;
      const saved=await send<Preview>(`${endpoint}/publication-draft`,{...prepared,document_generations},"PUT");
      if(token!==documentGeneration.current)return;
      setPreview(saved);
      setGeneratingDocuments(false);
      setConfirmation({...payload,document_generations,draft_id:saved.draft_id,draft_revision:saved.draft_revision});
    } catch(failure){
      if(token===documentGeneration.current){
        setError((failure as Error).message);setDocumentError(true);
        try{setWriters(await api<typeof writers>(`/analyses/${requestId}/goal/assistants`));}catch{/* Keep the drafting error visible. */}
      }
    } finally {if(token===documentGeneration.current){setBusy(false);setGeneratingDocuments(false);}}
  }
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
            const attempts = await api<Attempt[]>(`${endpoint}/publications${conversationTicketId ? "?conversation_ticket_id="+conversationTicketId : ""}`);
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
              const original = recoveryPayload(existing);
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
      if(data.status === "PUBLISHED") onPublished?.();
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
    if (generatingDocuments) {finishClose();return;}
    if (busy) return;
    if ((dirty || unified) && !pending) {
      setBusy(true);
      try {
        const content=await beforeSave?.();
        if(preview&&(dirty||content&&(content.title!==preview.title||content.body!==preview.body)))await saveDraft(content);
      }
      catch (error) { setError((error as Error).message); return; }
      finally { setBusy(false); }
    }
    finishClose();
  }
  function finishClose() {
    documentGeneration.current++;
    setBusy(false);setGeneratingDocuments(false);
    previewGeneration.current++;
    setConfirmation(null);
    dialog.current?.close();
    setOpen(false);
    setPreview(null);
    setResult(null);
    setDirty(false);
    setConnector("");
    setPending(null);
    setDraftSaveFailed(false);
    onClosed?.();
  }
const renderFields=(items:Field[])=>items.map((field) => (
                  <div key={field.id} className="field">
                    <label htmlFor={`${prefix}-publish-field-${field.id}`}>
                      {field.label}
                      {field.required ? " *" : ""}
                    </label>
                    {field.description && (
                      <p className="mb-2 text-xs muted">{field.description}</p>
                    )}
                    {field.type === "checkbox" ? (
                      <input
                        id={`${prefix}-publish-field-${field.id}`}
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
                        id={`${prefix}-publish-field-${field.id}`}
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
                        id={`${prefix}-publish-field-${field.id}`}
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
                        id={`${prefix}-publish-field-${field.id}`}
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
                ));
  const optionalControls=preview&&<>
    {!!preview.labels.length&&<CompactOptions label={t("Labels")} options={preview.labels} value={labels} onChange={next=>{setLabels(next);setDirty(true);}}/>}
    {!!preview.assignees.length&&<CompactOptions label={t("Assignees")} options={preview.assignees} value={assignees} single={connectors.find(item=>String(item.id)===connector)?.platform==="jira"} onChange={next=>{setAssignees(next);setDirty(true);}}/>}
                {(!!availableFiles.length||presentation.include_attachments)&&<fieldset className="mt-4 space-y-2 text-sm">
                  <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={presentation.include_attachments} onChange={event => change(() => { void recompose({ include_attachments: event.target.checked, ...(event.target.checked ? {} : { attachment_ids: [], include_goal: false, include_diagrams: false }) }); })} />{t("Include attachments")}{!!availableFiles.length&&<span className="muted"> · {availableFiles.length}</span>}</label>
                  {presentation.include_attachments && <div className="space-y-3">
                    <p className="text-xs muted">{t("Select each file to transfer. Original files and generated goal.md are separate choices.")}</p>
                    {availableFiles.map(file => <div key={file.id}>
                      <label className="flex items-start gap-2 text-sm"><input type="checkbox" disabled={!file.transferable} checked={file.kind === "goal" ? presentation.include_goal : file.kind === "diagrams" ? presentation.include_diagrams : presentation.attachment_ids.includes(file.id)} onChange={event => change(() => { void recompose(file.kind === "goal" ? { include_goal: event.target.checked } : file.kind === "diagrams" ? { include_diagrams: event.target.checked } : { attachment_ids: event.target.checked ? [...presentation.attachment_ids, file.id] : presentation.attachment_ids.filter(id => id !== file.id) }); })} /><span className="min-w-0 break-words">{file.name}<span className="ml-2 text-xs muted">{t(file.kind === "goal" ? "Generated goal.md" : file.kind === "diagrams" ? "Diagram annex (Mermaid)" : "Original attachment")} · {Math.ceil(file.size / 1024)} KB</span></span></label>
                      {!file.transferable && <p className="ml-6 mt-1 text-xs muted">{t(file.reason || "This connector cannot transfer this file.")}</p>}
                    </div>)}
                    {!preview.available_attachments?.length && <p className="text-xs muted">{t("No transferable files are available.")}</p>}
                  </div>}
                </fieldset>}
  </>;
  const templateControls=<>
              {preview && !!preview.templates.length && <div className="field sm:col-span-2">
                <label htmlFor="publish-format">{t("Ticket format")}</label>
                <select id="publish-format" value={presentation.ticket_format || "standard"} onChange={event => change(() => { void recompose({ ticket_format: event.target.value as "project" | "standard", ...(event.target.value === "project" ? { include_diagrams: false } : {}) }); })}>
                  <option value="project" disabled={!preview.templates.length}>{t("Project template")}</option>
                  <option value="standard">{t("Standard SpecHelper format")}</option>
                </select>
                {preview.fallback_reason && <p role="status" className="mt-2 text-xs muted">{t(preview.fallback_reason)}</p>}
              </div>}
              {!!preview?.templates.length && (
                <div className="field">
                  <label htmlFor={prefix+"-publish-template"}>
                    {t("Ticket template")}
                  </label>
                  <select
                    id={prefix+"-publish-template"}
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
  </>;
  const Surface = embedded ? "section" : "dialog";
  return (
    <>
      {!hideTrigger && <Button
        variant="outline"
        onClick={() => {
          setOpen(true);
          dialog.current?.showModal();
        }}
      >
        {t(triggerLabel)}
      </Button>}
      <Surface
        ref={embedded ? undefined : dialog}
        className={embedded ? `publication-surface${unified?" publication-unified":""}` : "publication-dialog publication-surface"}
        aria-labelledby={embedded ? undefined : `publication-title-${prefix}`}
        aria-label={embedded ? t("Publication destination") : undefined}
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
      >
        {!embedded && <div className="ticket-modal-header flex items-start justify-between gap-4">
          <div>
            <h2 id={`publication-title-${prefix}`}>{t("Publish ticket")}</h2>
            <p className="mt-1 text-sm muted">
              {version ? t("Publish analysis version {number}. The saved analysis will remain unchanged.", {number:version}) : t("Review and publish the conversation draft.")}
            </p>
          </div>
          <Button type="button" variant="ghost" onClick={close}>
            {t("Close")}
          </Button>
        </div>}
        {error && (
          <p
            role="alert"
            className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-red-800"
          >
            {t(error)}
          </p>
        )}
        {documentError&&<div className="mt-3 space-y-2 text-sm">
          <p>{t("Document generation failed. No ticket was sent. Retry or deselect the affected documents.")}</p>
          {!!writers.length&&<label>{t("Writing assistant")}<select value={writer} onChange={event=>setWriter(event.target.value)}><option value="">{t("Conversation assistant")}</option>{writers.map(item=><option key={item.connection_id} value={item.connection_id}>{item.name} · {item.model}</option>)}</select></label>}
          <Button type="button" variant="outline" disabled={busy} onClick={()=>(document.getElementById(`publication-form-${prefix}`) as HTMLFormElement|null)?.requestSubmit()}>{t("Retry")}</Button>
        </div>}
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
            {ticketUrl(result.url) && (
              <a
                className="mt-4 inline-block text-primary underline"
                href={ticketUrl(result.url)!}
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
          <form id={`publication-form-${prefix}`}
            onSubmit={async (event) => {
              event.preventDefault();
              if (!preview || preview.publication_allowed === false || confirmation || disabled || busy) return;
              setBusy(true);
              let current = preview;
              let content:{title:string;body:string}|undefined;
              try { content=await beforeSave?.(); current = await saveDraft(content); }
              catch (error) { setError((error as Error).message); setBusy(false); return; }
              const candidate:Payload = {
                conversation_ticket_id:conversationTicketId,
                ...presentation,
                draft_id: current.draft_id,
                draft_revision: current.draft_revision,
                connector_id: Number(connector),
                project,
                title:content?.title??title,
                body:content?.body??body,
                fields,
                labels,
                assignees,
                template_id: template,
                issue_type: issueType,
                options_revision: preview.revision,
                idempotency_key: crypto.randomUUID(),
                confirmed: true,
              };
              await prepareAndConfirm(candidate);setBusy(false);
            }}
          >
            {!connectors.length && (
              <p className="mt-5 muted">
                {t("No publication connection is associated with this environment.")}{" "}
                <a className="text-primary underline" href="/admin?tab=environments" target="_blank" rel="noopener noreferrer">{t("Configure publication destinations")}<span className="sr-only"> · {t("Opens in a new tab")}</span></a>
              </p>
            )}
            {unified&&<h3 className="font-medium text-sm">{t("Publication")}</h3>}
            <fieldset disabled={busy||!!confirmation||disabled} className="grid gap-x-4 sm:grid-cols-2">
              <div className="field">
                <label htmlFor={prefix+"-publish-connector"}>{t("Publication connection")}</label>
                <select
                  id={prefix+"-publish-connector"}
                  required
                  value={connector}
                  onChange={(e) => change(() => setConnector(e.target.value))}
                >
                  <option value="">{t("Select a connector")}</option>
                  {connectors.map((c) => (
                    <option key={c.id} value={c.id} disabled={c.enabled === false || c.status !== "CONNECTED"}>
                      {c.name} · {publicationPlatforms[c.platform] || c.platform}{c.enabled === false ? ` · ${t("Disabled")}` : c.status !== "CONNECTED" ? ` · ${t(c.status === "UNKNOWN" ? "Not tested" : c.status === "UNAVAILABLE" ? "Verification unavailable" : "Failed")}` : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor={prefix+"-publish-project"}>
                  {t("Project / repository")}
                </label>
                <select
                  id={prefix+"-publish-project"}
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
              {!unified&&templateControls}
              {!!preview?.issue_types.length && (
                <div className="field">
                  <label htmlFor={prefix+"-publish-issue-type"}>{t("Issue type")}</label>
                  <select
                    id={prefix+"-publish-issue-type"}
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
                {t(generatingDocuments?"Generating selected documents…":"Loading publication options…")}
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
              <fieldset disabled={busy||!!confirmation||disabled}>
                {!unified && preparedDraft && (title !== preparedDraft.title || body !== preparedDraft.body) && <div className="mt-4 space-y-2"><Button type="button" variant="outline" onClick={() => { setTitle(preparedDraft.title); setBody(preparedDraft.body); setDirty(true); }}>{t("Use prepared draft")}</Button></div>}
                {preview.notice && (
                  <p className="mt-4 rounded border bg-muted p-3 text-sm">
                    {t(preview.notice)}
                  </p>
                )}
                {renderFields(preview.fields.filter(field=>!unified||field.required))}
                {!unified&&optionalControls}
                {!unified&&<>
                <h3 className="mt-6">{t("Publication preview")}</h3>
                <p className="mt-2 break-words text-sm font-semibold">{title}</p>
                <p className="mt-1 flex items-center gap-2 text-xs muted"><ProviderLogo provider={connectors.find(item => String(item.id) === connector)?.platform} />{version ? t("Analysis version {number}", { number: version }) : t("Conversation draft")} · {projects.find(item => item.id === project)?.name || project}</p>
                <div className="mt-3 text-sm"><MarkdownReader>{shortPreview}</MarkdownReader></div>
                <details className="mt-3 text-sm"><summary className="cursor-pointer">{t("See full content")}</summary><div className="mt-3"><MarkdownReader>{renderedBody}</MarkdownReader></div></details>
                <p className="my-4 text-xs muted">{t("The ticket will be created on the selected platform. No source code will be modified.")}</p>
                </>}
                {!!publicationIssues.length && <div id={`publication-issues-${prefix}`} role="status" className="mb-4 rounded-lg border border-amber-500/50 p-4 text-sm">
                  <p className="font-semibold">{t("Publication is blocked")}</p>
                  <ul className="mt-2 list-disc pl-5">{publicationIssues.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
                  {preview.publication_allowed === false && <p className="mt-2 muted">{t("You can review and save this draft. Exporting it does not complete the missing checks.")}</p>}
                </div>}
              </fieldset>
            )}
            {(unified||!!documents.length)&&<fieldset className="mt-3 space-y-2 text-sm" disabled={busy||!!confirmation||disabled}>
              <legend className="font-medium">{t("Documents to attach")} <span className="font-normal muted">· {t("Optional")}</span></legend>
              <div className="flex flex-wrap gap-x-5 gap-y-2">{(unified?["goal","business","technical"]:documents).map(kind=><label key={kind} className="flex items-center gap-2"><input type="checkbox" checked={selectedDocuments.includes(kind)} onChange={event=>{
                const next=event.target.checked?[...selectedDocuments,kind]:selectedDocuments.filter(item=>item!==kind);
                setSelectedDocuments(next);onDocumentsChange?.(next);setDocumentError(false);setError("");
              }}/>{t(kind==="goal"?"goal.md":kind==="business"?"Business report":"Technical report")}</label>)}</div>
            </fieldset>}
            {unified&&<details className="mt-4 text-sm">
              <summary className="cursor-pointer font-medium">{t("Additional options")}</summary>
              <fieldset disabled={busy||!!confirmation||disabled} className="mt-3 space-y-3">
                {advancedContent}
                {templateControls}
                {preview&&renderFields(preview.fields.filter(field=>!field.required))}
                {optionalControls}
              </fieldset>
            </details>}
          </form>
        )}
        {confirmation&&<div ref={confirmationPanel} tabIndex={-1} className="mt-4 rounded-md border p-4 space-y-3" role="alertdialog" aria-label={t(preview?.requires_unverified_confirmation?"Publish without independent verification":"Confirm publication")}>
          <p>{t(preview?.requires_unverified_confirmation?"This ticket has not been verified by a deep analysis. Publish it anyway?":"Confirm creation of this ticket on the selected platform?")}</p>
          <div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={()=>{const payload=confirmation;setConfirmation(null);void publish({...payload,unverified_confirmed:!!preview?.requires_unverified_confirmation});}}>{t(preview?.requires_unverified_confirmation?"Publish anyway":"Confirm publication")}</Button>
          {onAnalyze&&preview?.requires_unverified_confirmation&&<Button variant="outline" disabled={busy} onClick={()=>{finishClose();onAnalyze();}}>{t("Launch deep analysis")}</Button>}
          <Button variant="ghost" disabled={busy} onClick={()=>setConfirmation(null)}>{t("Cancel")}</Button></div>
        </div>}
        {!hideFooter&&<div className="ticket-modal-footer mt-4">
          <Button type="button" variant="outline" disabled={busy&&!generatingDocuments} onClick={close}>
            {t(unified?"Close":"Back")}
          </Button>
          {footerActions}
          {!unified&&draftSaveFailed&&<Button type="button" variant="ghost" disabled={busy} onClick={finishClose}>{t("Close without saving")}</Button>}
          {!pending&&(!result||result.status==="ERROR")&&!recovering&&!recoveryFailed&&!confirmation&&<Button type="submit" form={`publication-form-${prefix}`} disabled={busy||disabled||!preview||publicationIssues.length>0} aria-describedby={publicationIssues.length?`publication-issues-${prefix}`:undefined}>{t("Publish")}</Button>}
        </div>}
      </Surface>
    </>
  );
}
