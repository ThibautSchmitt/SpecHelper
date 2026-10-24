export type EvidenceStatus = "supported" | "partial" | "contradicted" | "unverified";
export type EvidenceKind = "observed" | "interpretation" | "contradiction" | "unknown";

export type GitEvidenceSource = {
  kind: "git";
  repository: string;
  commit: string;
  path: string;
  symbol: string;
  line_start: number;
  line_end: number;
  excerpt: string;
};
export type SQLEvidenceSource = { kind: "sql"; query_id: string };
export type WebEvidenceSource = { kind: "web"; reference_id: string; excerpt: string; authority: string; effective_date: string; version: string; jurisdiction: string; scope: string; applicability: "current" | "historical" | "unknown"; applicability_notes: string };
export type WebReceipt = { reference_id: string; url: string; title: string; consulted_at: string; published_at: string; sha256: string; text_sha256: string; text: string; truncated: boolean; status: "checked" };
export type SQLReceipt = {
  query_id: string;
  sql: string;
  checked_at: string;
  status: "checked" | "unavailable" | "rejected";
  row_count: number;
  truncated: boolean;
  rows_exposed: number;
};
export type AnalysisClaim = {
  id: string;
  statement: string;
  kind: EvidenceKind;
  status: EvidenceStatus;
  scope: {
    environment: string;
    conditions: string[];
    period: string;
    population: string;
    sample_limits: string;
  };
  sources: (GitEvidenceSource | SQLEvidenceSource | WebEvidenceSource)[];
  basis?: "deployment" | "official_rule" | "external_contract";
  counterexamples: {
    description: string;
    interpretation: "current_behavior" | "historical_anomaly" | "unknown";
  }[];
  verification_notes: string;
  universal: boolean;
  material: boolean;
};
export type ReliabilityReport = {
  claims: AnalysisClaim[];
  database: {
    status: "not_configured" | "checked" | "unavailable" | "not_checked";
    scope: string;
    limitations: string[];
    checks: SQLReceipt[];
  };
  limitations: string[];
  blocking: boolean;
  web_references?: WebReceipt[];
};
