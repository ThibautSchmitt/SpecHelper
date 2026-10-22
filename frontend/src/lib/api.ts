import type { AnalysisWarning } from "@/lib/orchestration";

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
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
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string" ? body.detail : "Check the form fields";
    } catch {}
    throw new Error(message);
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
export type RequestItem = {
  id: string;
  need: string;
  confrontation: boolean;
  language: "en" | "fr";
  status: string;
  environment_id: number | null;
  environment_name: string;
  created_at: string;
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
  artifacts: Record<string, string>;
};
export type RequestDetail = RequestItem & {
  analysis_runs?: {
    number: number;
    status: string;
    warnings?: AnalysisWarning[];
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
  questions: { id: string; question: string }[];
  conversation: {
    questions: { id: string; question: string }[];
    answers: Record<string, string>;
  }[];
  understanding: string;
  progress: { label: string; at: string }[];
  error: string;
  attachments: { id: string; name: string; size: number }[];
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
};
