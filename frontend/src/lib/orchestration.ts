export const publicRoles = ["analyst", "counter_analyst", "verifier"] as const;
export type PublicRole = (typeof publicRoles)[number];
export const roleLabels: Record<string, string> = {
  analyst: "Analyst",
  counter_analyst: "Counter-analyst",
  verifier: "Verifier",
  library_generator: "Definition generator",
  library_test: "Definition sandbox test",
};
export type AnalysisWarning =
  | string
  | { code?: string; role?: string; message: string };
export function warningMessage(warning: AnalysisWarning): string {
  return typeof warning === "string" ? warning : warning.message;
}

export function modelFamilyDiversity(steps?: { public_role?: string; status?: string; model_family?: string }[]) {
  if (!steps?.length) return "Model-family diversity not recorded";
  const completed = new Map<string, string>();
  for (const step of steps) if (step.public_role && publicRoles.includes(step.public_role as PublicRole) && step.status === "DONE") completed.set(step.public_role, step.model_family || "");
  if (publicRoles.some(role => !completed.has(role))) return "Missing step · incomplete verification";
  if (publicRoles.some(role => !completed.get(role))) return "Model-family diversity not recorded";
  const count = new Set(completed.values()).size;
  return count === 3 ? "Three model families · full diversity" : count === 2 ? "Two model families · partial diversity" : "One model family · limited diversity";
}
