export const publicRoles = ["analyst", "counter_analyst", "verifier"] as const;
export type PublicRole = (typeof publicRoles)[number];
export const roleLabels: Record<string, string> = {
  analyst: "Analyst",
  counter_analyst: "Counter-analyst",
  verifier: "Verifier",
};
export type AnalysisWarning = string | { code?: string; role?: string; message: string };
export function warningMessage(warning: AnalysisWarning): string {
  return typeof warning === "string" ? warning : warning.message;
}
