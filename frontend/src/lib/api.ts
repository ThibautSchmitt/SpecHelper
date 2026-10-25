import { secureFetch } from "@/lib/access";
import type { AnalysisWarning } from "@/lib/orchestration";
import type { ContextSnapshot, ContextUsage } from "@/lib/context";
import type { BusinessDecision, BusinessSummary, ClarificationQuestion } from "@/lib/business-decisions";
import type { ReliabilityReport } from "@/lib/analysis-evidence";

export class APIError extends Error {
  constructor(message: string, public status: number, public details?: unknown) {
    super(message);
    this.name = "APIError";
  }
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await secureFetch(`/api${path}`, {
    cache: "no-store",
    ...options,
    headers: {
      ...(options?.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options?.headers,
    },
  });
  if (!response.ok) {
    let message = `Error ${response.status}`;
    let details: unknown;
    try {
      const body = await response.json();
      details = body;
      message =
        typeof body.detail === "string" ? body.detail : "Check the form fields";
    } catch {}
    throw new APIError(message, response.status, details);
  }
  return response.json();
}
export function send<T>(path: string, body?: unknown, method = "POST") {
  return api<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
export type Environment = {
  id: number;
  name: string;
  revision: number;
  status: string;
  error: string;
  database_id: number | null;
  database_name: string | null;
  repositories: {
    id: number;
    repository: string;
    git_connection_id?: number;
    connection_name?: string;
    remote_id?: string;
    path?: string;
    provider?: string;
    is_fork?: boolean;
    parent?: { path: string; url: string } | null;
    branch: string;
    sha: string;
  }[];
};
export type ScopeAssessment = {
  status: "IN_SCOPE" | "OUT_OF_SCOPE" | "NEEDS_CLARIFICATION";
  reason_code: string;
  policy_version: string;
  message: string;
  question: string;
  operation?: string;
  revision?: number;
  assessed_at?: string;
};
export function scopeNeedsContext(assessment?: ScopeAssessment | null) {
  return assessment?.status === "OUT_OF_SCOPE" || assessment?.status === "NEEDS_CLARIFICATION";
}
export type RequestItem = {
  id: string;
  need: string;
  title?: string;
  updated_at?: string;
  workflow?: "request" | "question";
  category?: string;
  confrontation: boolean;
  language: "en" | "fr";
  status: string;
  environment_id: number | null;
  environment_name: string;
  created_at: string;
  original_need?: string;
  scope_assessment?: ScopeAssessment | null;
  scope_clarification?: string;
  scope_pending_message?: string;
  scope_revision?: number;
};
export type ResultVersion = {
  id: string;
  number: number;
  format_version: string;
  language: "en" | "fr";
  status: string;
  created_at: string;
  ticket: Record<string, string | string[]>;
  markdown: string;
  goal_markdown: string;
  answer_markdown?: string;
  explanation?: { title: string; [key: string]: unknown };
  artifacts: Record<string, string>;
  run_number?: number;
  decisions_snapshot?: BusinessDecision[];
  business_summary?: BusinessSummary;
  evidence?: ReliabilityReport;
  context_snapshot?: ContextSnapshot;
  context_usage?: ContextUsage[];
};
export type RequestDetail = RequestItem & {
  analysis_protocol?: string;
  evidence?: ReliabilityReport;
  decisions?: BusinessDecision[];
  decision_history?: BusinessDecision[];
  decision_revision?: number;
  validated_version?: number | null;
  business_summary?: BusinessSummary;
  source_question?: { id: string; version: number; title?: string } | null;
  derived_requests?: {
    id: string;
    need: string;
    status: string;
    source_version?: number;
  }[];
  analysis_runs?: {
    number: number;
    status: string;
    warnings?: AnalysisWarning[];
    context_snapshot?: ContextSnapshot;
    context_usage?: ContextUsage[];
    steps: {
      public_role?: string;
      model_family?: string;
      warnings?: AnalysisWarning[];
      conclusions?: string[];
      step?: string;
      role?: string;
      roles?: string[];
      connection_name?: string;
      agent?: string;
      provider?: string;
      model?: string;
      status?: string;
      error?: string;
      failure?: string;
      diagnostic?: string;
      instruction_snapshot?: {
        global_instructions?: string;
        global_instruction_version?: number;
        connection_instructions?: { additional_instructions?: string; version?: string };
        public_role?: string;
      };
      loaded_skills?: { slug: string; name?: string; version: number; sha256?: string }[];
      skills_audit?: "observed" | "unavailable";
    }[];
    error?: string;
  }[];
  baseline: {
    repository: string;
    branch: string;
    sha: string;
    path?: string;
    connection_name?: string;
    is_fork?: boolean;
    parent?: { path: string } | null;
  }[];
  database: { name?: string };
  questions: ClarificationQuestion[];
  conversation: {
    questions: { id: string; question: string }[];
    answers: Record<string, string>;
  }[];
  understanding: string;
  progress: { label: string; at: string }[];
  error: string;
  attachments: {
    id: string;
    name: string;
    size: number;
    internal?: boolean;
    source_question?: { id: string; version: number } | null;
  }[];
  ticket: Record<string, string | string[]> | null;
  markdown: string | null;
  latest_version: ResultVersion | null;
  versions: { number: number; created_at: string; status: string }[];
  messages: {
    id: number;
    role: string;
    kind: string;
    content: string;
    version_number: number | null;
  }[];
};
export const statuses: Record<string, string> = {
  DONE: "Completed",
  RUNNING: "Analyzing",
  DRAFT: "Draft",
  QUEUED: "Queued",
  UNDERSTANDING: "Understanding your need",
  NEEDS_CLARIFICATION: "Needs clarification",
  ANALYZING: "Analyzing",
  REVIEWING: "Reviewing the proposal",
  GENERATING_RESULT: "Preparing the result",
  CONTINUING_CONVERSATION: "Continuing the discussion",
  GENERATING_TICKET: "Writing the ticket",
  READY: "Completed",
  PARTIAL: "Partial result",
  ERROR: "Interrupted",
  PENDING: "Queued",
  SYNCING: "Synchronizing",
  CONNECTED: "Connected",
  AVAILABLE: "Available",
  BUSY: "Busy",
  QUOTA_EXHAUSTED: "Quota exhausted",
  DISCONNECTED: "Disconnected",
  UNKNOWN: "Unknown",
  MODEL_UNAVAILABLE: "Model unavailable",
  AUTH_ERROR: "Authentication error",
  DISABLED: "Disabled",
  CANCELLED: "Cancelled",
  WAITING_AI: "Waiting for AI",
};

export type QuestionDocument = {
  id: string;
  kind: "business" | "technical" | "mixed";
  markdown: string;
  source_version: number;
  language: "en" | "fr";
  created_at: string;
  download_url: string;
};
export type QuestionTransfer = {
  name: string;
  content: string;
  source_question_id: string;
  source_version: number;
  environment_id: number | null;
  baseline: RequestDetail["baseline"];
  language: "en" | "fr";
};
