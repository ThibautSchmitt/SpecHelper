export type BusinessOption = {
  id: string;
  label: string;
  behavior: string;
  relevance: string;
  benefits: string;
  limitations: string;
  consequences: string;
};

export type ClarificationQuestion = {
  id: string;
  question: string;
  kind?: "free" | "choice";
  decision_key?: string;
  options?: BusinessOption[];
  reason?: string;
  unknowns?: string[];
  conflicts_with?: number | null;
};

export type BusinessDecision = {
  id: number;
  sequence: number;
  key: string;
  question: ClarificationQuestion;
  option_id: string | null;
  option: BusinessOption | null;
  value: string;
  previous_id: number | null;
  source_version: number | null;
  created_at: string;
};

export type BusinessSummary = {
  current?: string;
  desired?: string;
  gap?: string;
  impacts?: string[];
  uncertainties?: string[];
};

export type DecisionConflict = {
  decision_id: number;
  key: string;
  previous: BusinessDecision;
  proposed: {
    question: ClarificationQuestion;
    option_id: string | null;
    option: BusinessOption | null;
    value: string;
  };
};

export type ConflictResponse = {
  code: "DECISION_CONFLICT";
  detail: string;
  conflicts: DecisionConflict[];
  decision_revision: number;
};
