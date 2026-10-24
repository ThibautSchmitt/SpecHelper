export type ContextResource = {
  id: string; version_id: string; name: string; filename: string;
  version: number; sha256: string; size: number; content_type: string;
  agent_readable: boolean;
};
export type ContextSnapshot = {
  schema_version?: number; snapshot_id?: string;
  analysis_protocol?: string;
  environment?: { id: number; name: string; revision: number };
  instructions?: { text: string; enabled: boolean; sha256: string; mode?: "factual" | "instructions" };
  resources?: ContextResource[];
  official_references?: { url: string; note: string }[];
  library?: {
    agents?: {slug: string; name: string; version: number; instructions?: string}[];
    skills?: {slug: string; name: string; version: number; instructions?: string}[];
  };
};
export type ContextUsage = {
  version_id: string; public_role?: string;
  status: "observed" | "not_observed" | "unavailable";
};
