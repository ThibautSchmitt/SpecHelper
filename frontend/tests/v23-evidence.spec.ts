import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import type { RequestDetail, ResultVersion } from "../src/lib/api";
import type { ReliabilityReport, AnalysisClaim } from "../src/lib/analysis-evidence";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const id = "23232323-2323-4232-8232-232323232323";
const timestamp = "2026-10-24T10:00:00Z";
function report(): ReliabilityReport {
  const base: AnalysisClaim = { id: "observed", statement: "The cancellation control checks active benefits.", kind: "observed", status: "supported", scope: { environment: "Production", conditions: ["Standard cancellation only"], period: "January through September 2026", population: "42 closed contracts", sample_limits: "Archived contracts were excluded." }, sources: [{ kind: "git", repository: "business-app", commit: "frozen-commit-v1", path: "contracts/cancel.py", symbol: "cancel_contract", line_start: 12, line_end: 16, excerpt: "if active_benefits: reject_cancellation()" }, { kind: "sql", query_id: "check-23" }], counterexamples: [], verification_notes: "The checked scope does not cover supervisor overrides.\nNo counterexample found does not establish universal validity.", universal: false, material: false };
  return { claims: [base, { ...base, id: "partial", statement: "Supervisor overrides may bypass the control.", status: "partial", kind: "interpretation", sources: [], universal: true }, { ...base, id: "contradiction", statement: "Some closed contracts still have active benefits.", kind: "contradiction", status: "contradicted", sources: [], material: true, counterexamples: [{ description: "Two older contracts contain an unresolved benefit.", interpretation: "historical_anomaly" }] }, { ...base, id: "unknown", statement: "The current exception process is unknown.", kind: "unknown", status: "unverified", sources: [] }], database: { status: "checked", scope: "Production: 42 closed contracts, January–September 2026", limitations: ["Historical imports may contain inconsistent records.", "Database observations apply only to the queried population and time."], checks: [{ query_id: "check-23", sql: "SELECT COUNT(*) FROM contracts WHERE state = ?", checked_at: timestamp, status: "checked", row_count: 1, truncated: false, rows_exposed: 1 }] }, limitations: ["Supervisor overrides require another focused check.", "Independent analysis, counter-analysis and verification have not all been completed."], blocking: true };
}
function version(number: number, evidence = report(), workflow = "request"): ResultVersion {
  return { id: `version-${number}`, number, status: "PARTIAL", format_version: "2.3", language: "en", created_at: timestamp, ticket: workflow === "request" ? { title: `Cancellation v${number}`, context: "Close contracts", need: "Check benefits", expected_behavior: [], proposed_solution: "Clarify exceptions", technical_impact: [], risks: [], acceptance_criteria: [] } : {}, markdown: "# Cancellation", goal_markdown: "# Goal", artifacts: {}, decisions_snapshot: [], evidence, ...(workflow === "question" ? { explanation: { title: "Cancellation explanation" }, answer_markdown: "The behavior needs a focused check." } : {}) };
}
function detail(workflow: "request" | "question", evidence = report()): RequestDetail {
  const latest = version(2, evidence, workflow);
  return { id, workflow, need: "Explain cancellation controls", environment_id: 1, environment_name: "Production", created_at: timestamp, language: "en", status: "PARTIAL", analysis_protocol: "2.3", evidence, confrontation: true, baseline: [], database: {}, questions: [], conversation: [], understanding: "Check exceptions before approving.", progress: [], error: "", attachments: [], latest_version: latest, versions: [{ number: 1, status: "PARTIAL", created_at: timestamp }, { number: 2, status: "PARTIAL", created_at: timestamp }], messages: [], ticket: null, markdown: null, decisions: [], decision_history: [], decision_revision: 0, validated_version: null };
}
async function setup(page: Page, language: "en" | "fr", workflow: "request" | "question", value: RequestDetail) {
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", primary_color: "#2563eb", language, allow_confrontation: true } }));
  for (const path of ["environments", "requests", "questions", "queue"]) await page.route(`**/api/${path}`, route => route.fulfill({ json: [] }));
  const base = workflow === "question" ? "questions" : "requests";
  await page.route(`**/api/${base}/${id}`, route => route.fulfill({ json: value }));
  await page.route(`**/api/${base}/${id}/versions/*`, route => route.fulfill({ json: version(1, report(), workflow) }));
  await page.route(`**/api/questions/${id}/versions/*/documents`, route => route.fulfill({ json: [] }));
  await page.addInitScript(language => localStorage.setItem("spechelper-theme", language === "fr" ? "dark" : "light"), language);
}
for (const language of ["en", "fr"] as const) {
  const t = (key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
  for (const workflow of ["request", "question"] as const) {
    test(`scoped findings, independent decisions and frozen sources: ${workflow} ${language}`, async ({ page }, info) => {
      const current = report(); current.claims[0].sources = [];
      const value = detail(workflow, current);
      const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
      await setup(page, language, workflow, value);
      const base = workflow === "question" ? "questions" : "requests";
      await page.goto(`/${base}/${id}`);
      await page.getByText(t("Verification details"), { exact: true }).click();
      const panel = page.getByRole("region", { name: t("Analysis findings and limits"), exact: true });
      for (const label of ["Supported finding", "Partially supported", "Contradicted", "Not verified"]) await expect(panel.getByText(t(label), { exact: true })).toBeVisible();
      for (const label of ["Observed fact", "Interpretation", "Contradiction", "Unknown"]) await expect(panel.locator("article > p").filter({ hasText: new RegExp(`^${t(label)} ·`) })).toBeVisible();
      expect(await panel.getByRole("heading", { name: "The cancellation control checks active benefits.", exact: true }).evaluate(element => element.getBoundingClientRect().width)).toBeGreaterThan(180);
      await expect(panel).toContainText("42 closed contracts");
      await expect(panel).toContainText("The checked scope does not cover supervisor overrides.");
      for (const note of ["No counterexample found does not establish universal validity.", "Database observations apply only to the queried population and time.", "Independent analysis, counter-analysis and verification have not all been completed."]) await expect(panel).toContainText(t(note));
      await expect(panel).toContainText("Standard cancellation only");
      await expect(panel).toContainText(t("Historical inconsistency"));
      await expect(panel).toContainText(t("Finding no counterexample in the queried records does not establish that no exception is possible."));
      await expect(page.getByRole("region", { name: t("Confirmed business decisions"), exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: t("Validate business intent"), exact: true })).toHaveCount(0);
      await page.getByLabel(t("Result version"), { exact: true }).selectOption("1");
      await page.getByText(t("Verification details"), { exact: true }).click();
      await expect(panel).toContainText(t("These findings and limits belong to the displayed result version."));
      await expect(panel.getByText(/frozen-commit-v1/)).not.toBeVisible();
      const disclosure = panel.getByText(t("Sources and verification details"), { exact: true });
      await disclosure.focus(); await disclosure.press("Enter");
      await expect(panel.getByText(/frozen-commit-v1/)).toBeVisible();
      await expect(panel.getByText(/SELECT COUNT/)).toBeVisible();
      await expect(panel).toContainText(t("Returned rows: {count}").replace("{count}", "1"));
      await expect(panel.getByText(/\d+%/)).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
      await page.screenshot({ path: `../.local/v23-evidence/${workflow}-${language}-${info.project.name}.png`, fullPage: true });
    });
    for (const status of ["not_configured", "unavailable", "not_checked"] as const) test(`honest database state ${status}: ${workflow} ${language}`, async ({ page }) => {
      const evidence = report(); evidence.database = { status, scope: "", limitations: [], checks: [] }; evidence.claims = [];
      await setup(page, language, workflow, detail(workflow, evidence));
      await page.goto(`/${workflow === "question" ? "questions" : "requests"}/${id}`);
      await page.getByText(t("Verification details"), { exact: true }).click();
      const panel = page.getByRole("region", { name: t("Analysis findings and limits"), exact: true });
      const labels = { not_configured: "No business database is configured. Real records were not checked.", unavailable: "The business database could not be checked. Conclusions about real records remain unverified.", not_checked: "Business database records were not checked for this analysis." };
      await expect(panel).toContainText(t(labels[status]));
      await expect(panel).not.toContainText(t("Read-only database checks were completed within the scope shown below."));
      await expect(page.getByRole("button", { name: t("Validate business intent"), exact: true })).toHaveCount(0);
    });
  }
  test(`blocking evidence cannot be approved even with READY status in ${language}`, async ({ page }) => {
    const value = detail("request"); value.status = "READY";
    value.latest_version!.status = "READY";
    value.result_state = "partial";
    await setup(page, language, "request", value);
    await page.goto(`/requests/${id}`);
    await expect(page.getByLabel(t("Result reliability"), { exact: true })).toContainText(t("Partial result"));
    await expect(page.getByLabel(t("Result reliability"), { exact: true })).toContainText("Supervisor overrides require another focused check.");
      await page.getByText(t("Verification details"), { exact: true }).click();
    await expect(page.getByRole("region", { name: t("Analysis findings and limits"), exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: t("Validate business intent"), exact: true })).toHaveCount(0);
  });
  test(`mandatory independent review administration in ${language}`, async ({ page }) => {
    await setup(page, language, "request", detail("request"));
    await page.route("**/api/system", route => route.fulfill({ json: { jobs: [] } }));
    await page.route("**/api/connections", route => route.fulfill({ json: { github: { status: "CONNECTED" }, ais: [], databases: [] } }));
    let body: Record<string, unknown> | null = null;
    const settings = { reliability_protocol: "2.3", allow_confrontation: true, verifier_enabled: true, allow_same_family_fallback: true, max_calls: 12, timeout_seconds: 240, role_instructions: { analyst: "Check", counter_analyst: "Challenge", verifier: "Find exceptions" }, active_internal_agents: ["code", "reviewer"], default_skills: [], available_agents: [{ slug: "code", name: "Code inspection", required: true }, { slug: "reviewer", name: "Evidence review", required: true }], available_skills: [] };
    await page.route("**/api/orchestration-settings", route => { if (route.request().method() === "PUT") body = route.request().postDataJSON(); return route.fulfill({ json: settings }); });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    await page.getByRole("button", { name: t("Roles and orchestration"), exact: true }).click();
    await expect(page.getByText(t("Independent review is required"), { exact: true })).toBeVisible();
    await expect(page.getByLabel(t("Verify compared analyses"), { exact: true })).toHaveCount(0);
    await expect(page.getByLabel(t("Allow comparison of multiple analyses"), { exact: true })).toHaveCount(0);
    await page.locator("summary").filter({ hasText: t("Advanced options") }).click();
    const calls = page.getByLabel(t("Maximum AI calls per analysis")); await expect(calls).toHaveAttribute("min", "6"); await calls.fill("8");
    await page.getByRole("button", { name: t("Save analysis settings"), exact: true }).click();
    await expect.poll(() => body).toMatchObject({ allow_confrontation: true, verifier_enabled: true, max_calls: 8 });
    expect(body).not.toHaveProperty("reliability_protocol"); expect(body).not.toHaveProperty("available_agents");
  });
}
