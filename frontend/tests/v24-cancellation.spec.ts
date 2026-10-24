import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const id = "24242424-2424-4242-8242-242424242424";
function detail(workflow: "request" | "question") {
  return { id, workflow, analysis_protocol: "2.4", need: "Check export boundaries", status: "ANALYZING", language: "en", environment_id: 1, environment_name: "Production", created_at: "2026-10-24T10:00:00Z", confrontation: true, baseline: [], database: {}, questions: [], conversation: [], progress: [], understanding: "Check rare states", error: "", attachments: [], ticket: null, markdown: null, versions: [], latest_version: null, messages: [] };
}
async function setup(page: Page, language: "en" | "fr") {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb" } }));
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "fr" ? "dark" : "light");
}
for (const language of ["en", "fr"] as const) {
  const t = (key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
  for (const workflow of ["request", "question"] as const) test(`cancel the current ${workflow} without a five-minute promise in ${language}`, async ({ page }) => {
    await setup(page, language);
    const base = workflow === "question" ? "questions" : "requests";
    let value = detail(workflow);
    await page.route(`**/api/${base}/${id}`, route => route.fulfill({ json: value }));
    let cancellations = 0;
    await page.route(`**/api/${base}/${id}/cancel`, route => { cancellations += 1; expect(route.request().method()).toBe("POST"); value = { ...value, status: "CANCELLED" }; return route.fulfill({ json: value }); });
    await page.goto(`/${base}/${id}`);
    await expect(page.getByText(t("The analysis continues until its checks are complete. You can leave this page and return later."), { exact: true })).toBeVisible();
    await expect(page.getByText(t("An analysis is limited to five minutes once started. You can leave this page and return later."), { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: t("Cancel analysis"), exact: true }).click();
    await expect.poll(() => cancellations).toBe(1);
    await expect(page.getByRole("heading", { name: t("Analysis cancelled"), exact: true })).toBeVisible();
    await expect(page.getByText(t("Execution has stopped. Earlier results and recorded evidence remain available."), { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: t("Cancel analysis"), exact: true })).toHaveCount(0);
  });
  test(`a rejected cancellation remains visible and does not claim success in ${language}`, async ({ page }) => {
    await setup(page, language);
    await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: detail("request") }));
    await page.route(`**/api/requests/${id}/cancel`, route => route.fulfill({ status: 409, json: { detail: "The analysis state changed. Refresh before cancelling." } }));
    await page.goto(`/requests/${id}`);
    await page.getByRole("button", { name: t("Cancel analysis"), exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toHaveText(t("The analysis state changed. Refresh before cancelling."));
    await expect(page.getByRole("heading", { name: t("Analysis cancelled"), exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: t("Cancel analysis"), exact: true })).toBeEnabled();
  });
  test(`recorded instructions and actual skill loads remain distinct from availability in ${language}`, async ({ page }) => {
    await setup(page, language);
    const instructions = { global_instructions: "Frozen global instructions", global_instruction_version: 4, connection_instructions: { additional_instructions: "Frozen connection instructions", version: "a".repeat(64) }, public_role: "analyst" };
    const value = { ...detail("request"), analysis_runs: [{ number: 1, status: "RUNNING", context_snapshot: { schema_version: 1, analysis_protocol: "2.4", instructions: { text: "Archived contracts remain visible to auditors.", enabled: true, sha256: "c".repeat(64), mode: "factual" }, resources: [], library: { agents: [{ slug: "legacy-agent", name: "Legacy agent", version: 1, instructions: "Unused legacy agent instructions" }], skills: [] } }, steps: [
      { public_role: "analyst", connection_name: "ChatGPT team", agent: "codex", model: "recorded-model", status: "DONE", instruction_snapshot: instructions, skills_audit: "observed", loaded_skills: [{ slug: "billing-review", version: 3, sha256: "b".repeat(64) }] },
      { public_role: "counter_analyst", connection_name: "Claude team", agent: "claude", model: "recorded-model", status: "RUNNING", instruction_snapshot: { ...instructions, public_role: "counter_analyst" }, skills_audit: "unavailable", loaded_skills: [] },
    ] }] };
    await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: value }));
    await page.goto(`/requests/${id}`);
    await page.getByText(t("Analysis assignment history"), { exact: true }).click();
    await page.getByText(t("Frozen analysis context"), { exact: true }).click();
    await expect(page.getByText(t("Business terminology and factual context"), { exact: false })).toBeVisible();
    await expect(page.getByText("Unused legacy agent instructions", { exact: true })).toHaveCount(0);
    const disclosures = page.getByText(t("Recorded execution configuration"), { exact: true });
    await disclosures.first().click();
    const firstConfiguration = disclosures.first().locator("..");
    await expect(firstConfiguration.getByText("Frozen global instructions", { exact: true })).toBeVisible();
    await expect(firstConfiguration.getByText("Frozen connection instructions", { exact: true })).toBeVisible();
    await expect(page.getByText("billing-review · v3", { exact: false })).toBeVisible();
    await disclosures.last().click();
    await expect(page.getByText(t("Skill read telemetry is unavailable. Available skills are not evidence of use."), { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
