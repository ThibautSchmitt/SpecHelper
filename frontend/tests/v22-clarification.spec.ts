import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import type { RequestDetail, ResultVersion } from "../src/lib/api";
import type { BusinessDecision, BusinessSummary, ClarificationQuestion } from "../src/lib/business-decisions";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const id = "22222222-2222-4222-8222-222222222222";
const timestamp = "2026-10-24T10:00:00Z";
const rule: ClarificationQuestion = {
  id: "cancellation", question: "What should happen when benefits are still in progress?",
  kind: "choice", decision_key: "ongoing-benefits", reason: "This determines whether the contract can be closed.",
  unknowns: ["The current exception process has not been verified."],
  options: [
    { id: "block", label: "Block cancellation", behavior: "Keep the contract open until the benefits finish.", relevance: "Use this when every ongoing benefit must be resolved first.", benefits: "Prevents an inconsistent closure.", limitations: "The contract may stay open for a long time.", consequences: "The team must follow up on unresolved benefits." },
    { id: "warn", label: "Allow with a warning", behavior: "Show a warning and let the user continue.", relevance: "Use this when the team needs flexibility.", benefits: "Allows exceptional closures.", limitations: "A user may overlook an ongoing benefit.", consequences: "The team remains responsible for benefit follow-up." },
  ],
};
function decision(question = rule, optionId = "warn", text?: string, number = 1): BusinessDecision {
  const option = question.options?.find(item => item.id === optionId) || null;
  return { id: number, sequence: number, key: question.decision_key || question.id, question, option_id: optionId, option, value: text || option!.behavior, previous_id: number > 1 ? number - 1 : null, source_version: number > 1 ? 1 : null, created_at: timestamp };
}
const summary: BusinessSummary = { current: "The team cannot complete cancellation with an ongoing benefit.", desired: "Let the team continue after a warning.", gap: "A controlled exception is needed.", impacts: ["Benefit follow-up remains with the team."], uncertainties: ["Historical exceptions have not been checked."] };
function version(number: number, choices: BusinessDecision[], workflow = "request"): ResultVersion {
  const content = choices.map(item => item.value).join("\n");
  return { id: `v${number}`, number, status: "READY", format_version: "2.2", language: "en", created_at: timestamp, ticket: workflow === "question" ? {} : { title: `Cancellation proposal v${number}`, context: "Closing a contract", need: "Handle ongoing benefits", expected_behavior: [content], proposed_solution: "Apply the confirmed rule.", technical_impact: ["Verify the existing cancellation control."], risks: ["Historical exceptions remain uncertain."], acceptance_criteria: [content] }, markdown: `# Cancellation v${number}\n\n${content}`, goal_markdown: `# Goal v${number}\n\n${content}`, artifacts: {}, decisions_snapshot: structuredClone(choices), business_summary: number === 1 ? summary : { ...summary, desired: content }, ...(workflow === "question" ? { explanation: { title: `Cancellation explanation v${number}` }, answer_markdown: content } : {}) };
}
function detail(workflow: "request" | "question" = "request"): RequestDetail {
  return { id, workflow, need: "Make cancellation clear for the operations team.", environment_id: 1, environment_name: "Production", created_at: timestamp, language: "en", status: "NEEDS_CLARIFICATION", confrontation: false, baseline: [], database: {}, questions: [structuredClone(rule)], conversation: [], understanding: "Clarify how ongoing benefits affect cancellation.", progress: [], error: "", attachments: [], latest_version: null, versions: [], messages: [], ticket: null, markdown: null, decisions: [], decision_history: [], decision_revision: 0, validated_version: null };
}
async function setup(page: Page, language: "en" | "fr") {
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", primary_color: "#2563eb", language, allow_confrontation: true } }));
  await page.route("**/api/environments", route => route.fulfill({ json: [] }));
  await page.route("**/api/requests", route => route.fulfill({ json: [] }));
  await page.route("**/api/questions", route => route.fulfill({ json: [] }));
  await page.route("**/api/queue", route => route.fulfill({ json: [] }));
  await page.route(`**/api/questions/${id}/versions/*/documents`, route => route.fulfill({ json: [] }));
}

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
  test(`guided business rules, revision review and versioned approval in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
    let value = detail();
    const first = decision();
    const second = decision(rule, "block", undefined, 2);
    const firstVersion = version(1, [first]);
    const secondVersion = version(2, [second]);
    let reviseCalls = 0, confirmations = 0, validations = 0;
    await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: value }));
    await page.route(`**/api/requests/${id}/versions/*`, route => route.fulfill({ json: route.request().url().endsWith("/1") ? firstVersion : secondVersion }));
    await page.route(`**/api/requests/${id}/answers`, async route => {
      expect(route.request().postDataJSON()).toEqual({ answers: {}, choices: { cancellation: { option_id: "warn" } }, expected_decision_revision: 0 });
      value = { ...value, status: "QUEUED", questions: [], decisions: [first], decision_history: [first], decision_revision: 1 };
      await route.fulfill({ json: value });
      value = { ...value, status: "READY", latest_version: firstVersion, versions: [{ number: 1, created_at: timestamp, status: "READY" }], business_summary: summary };
    });
    await page.route(`**/api/requests/${id}/decisions/1/revise`, route => {
      reviseCalls++;
      const payload = route.request().postDataJSON();
      expect(payload).toMatchObject({ expected_decision_revision: 1, expected_version: 1, option_id: "block" });
      if (!payload.confirm_change) return route.fulfill({ status: 409, json: { code: "DECISION_CONFLICT", detail: "This answer changes a confirmed decision. Confirm the change or review your choice.", decision_revision: 1, conflicts: [{ decision_id: 1, key: first.key, previous: first, proposed: { question: rule, option_id: "block", option: rule.options![0], value: second.value } }] } });
      confirmations++;
      value = { ...value, status: "QUEUED", decisions: [second], decision_history: [first, second], decision_revision: 2 };
      return route.fulfill({ json: value });
    });
    await page.route(`**/api/requests/${id}/validation`, route => {
      expect(route.request().postDataJSON()).toEqual({ expected_version: 2, expected_decision_revision: 2 });
      if (route.request().method() === "POST") { validations++; value = { ...value, validated_version: 2 }; }
      else value = { ...value, validated_version: null };
      return route.fulfill({ json: value });
    });
    await page.addInitScript(({ language }) => { localStorage.setItem("spechelper-theme", language === "fr" ? "dark" : "light"); }, { language });
    await page.goto(`/requests/${id}`);
    const clarification = page.getByRole("region", { name: t("Business clarification") });
    await expect(clarification.getByRole("radio")).toHaveCount(3);
    await expect(clarification.locator("input:checked")).toHaveCount(0);
    await expect(clarification).toContainText(rule.options![0].limitations);
    await expect(clarification).toContainText(rule.options![1].consequences);
    await expect(clarification).toContainText(t("When this fits"));
    await expect(clarification).toContainText(t("Still to verify"));
    await expect(clarification.getByText(/recommended/i)).toHaveCount(0);
    await page.screenshot({ path: `../.local/v22-evidence/guided-${language}-${info.project.name}.png`, fullPage: true });
    await clarification.getByRole("button", { name: t("Validate and continue"), exact: true }).click();
    await expect(clarification.getByRole("alert")).toHaveText(t("Choose an option or describe another rule for every question."));
    const other = clarification.getByRole("radio", { name: /Other \/ clarify|Autre \/ Préciser/ });
    await other.check();
    await clarification.getByRole("button", { name: t("Validate and continue"), exact: true }).click();
    await expect(clarification.getByRole("alert")).toHaveText(t("Describe your alternative rule before continuing."));
    const optionA = clarification.getByRole("radio").nth(0);
    await optionA.focus(); await optionA.press("Space"); await optionA.press("ArrowDown");
    await expect(clarification.getByRole("radio").nth(1)).toBeChecked();
    await clarification.getByRole("button", { name: t("Validate and continue"), exact: true }).click();
    await expect(page.getByRole("heading", { name: t("Your request is queued"), exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Cancellation proposal v1", exact: true })).toBeVisible();
    const overview = page.getByRole("region", { name: t("Business overview") });
    await expect(overview).toContainText(t("Desired behavior"));
    await expect(overview).toContainText(summary.gap!);
    await expect(overview).toContainText(summary.uncertainties![0]);
    const panel = page.getByRole("region", { name: t("Confirmed business decisions") });
    await expect(panel).toContainText(first.value);
    await panel.getByRole("button", { name: t("Revise decision"), exact: true }).click();
    await panel.getByRole("radio").nth(0).check();
    await panel.getByRole("button", { name: t("Review this change"), exact: true }).click();
    await expect(panel.getByRole("region", { name: t("Review a changed decision") })).toBeVisible();
    expect(confirmations).toBe(0); expect(value.decisions![0].value).toBe(first.value);
    await panel.getByRole("button", { name: t("Review my choice"), exact: true }).click();
    await expect(panel.getByRole("button", { name: t("Confirm the change"), exact: true })).toHaveCount(0);
    await panel.getByRole("button", { name: t("Review this change"), exact: true }).click();
    await panel.getByRole("button", { name: t("Confirm the change"), exact: true }).click();
    expect(reviseCalls).toBe(3); expect(confirmations).toBe(1);
    await expect(page.getByRole("heading", { name: t("Your request is queued"), exact: true })).toBeVisible();
    value = { ...value, status: "READY", latest_version: secondVersion, versions: [{ number: 1, created_at: timestamp, status: "READY" }, { number: 2, created_at: timestamp, status: "READY" }], business_summary: secondVersion.business_summary };
    await expect(page.getByRole("heading", { name: "Cancellation proposal v2", exact: true })).toBeVisible();
    await page.getByLabel(t("Result version"), { exact: true }).selectOption("1");
    await expect(page.getByRole("heading", { name: "Cancellation proposal v1", exact: true })).toBeVisible();
    await expect(panel).toContainText(first.value);
    await expect(panel.getByRole("button", { name: t("Revise decision"), exact: true })).toHaveCount(0);
    await expect(panel.getByRole("button", { name: t("Validate business intent"), exact: true })).toHaveCount(0);
    await page.getByLabel(t("Result version"), { exact: true }).selectOption("latest");
    await expect(panel).toContainText(second.value);
    await panel.getByText(t("Decision history"), { exact: true }).click();
    await expect(panel).toContainText(first.value);
    await panel.getByRole("button", { name: t("Validate business intent"), exact: true }).click();
    expect(validations).toBe(1);
    await expect(panel.getByRole("button", { name: t("Revise decision"), exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: t("Continue the discussion"), exact: true })).toHaveCount(0);
    await panel.getByRole("button", { name: t("Reopen for changes"), exact: true }).click();
    await expect(panel.getByRole("button", { name: t("Revise decision"), exact: true })).toBeVisible();
    const ruleWidth = await panel.locator("ol").first().locator("li").first().locator("p").first().evaluate(element => element.getBoundingClientRect().width);
    expect(ruleWidth).toBeGreaterThan(120);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    await page.screenshot({ path: `../.local/v22-evidence/decisions-${language}-${info.project.name}.png`, fullPage: true });
  });

  test(`a conflicting answer keeps the existing rule until human confirmation in ${language}`, async ({ page }) => {
    await setup(page, language);
    const prior = decision(rule, "block");
    let value = { ...detail(), decisions: [prior], decision_history: [prior], decision_revision: 1, questions: [{ ...rule, conflicts_with: prior.id }] };
    const custom = "Only supervisors can continue after documenting the exception.";
    const calls: Record<string, unknown>[] = [];
    await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: value }));
    await page.route(`**/api/requests/${id}/answers`, route => {
      const payload = route.request().postDataJSON(); calls.push(payload);
      expect(payload).toMatchObject({ expected_decision_revision: 1, choices: { cancellation: { option_id: "other", text: custom } } });
      if (!payload.confirm_changes) return route.fulfill({ status: 409, json: { code: "DECISION_CONFLICT", detail: "This answer changes a confirmed decision. Confirm the change or review your choice.", decision_revision: 1, conflicts: [{ decision_id: prior.id, key: prior.key, previous: prior, proposed: { question: rule, option_id: "other", option: null, value: custom } }] } });
      value = { ...value, status: "QUEUED", questions: [], decisions: [decision(rule, "other", custom, 2)], decision_history: [prior, decision(rule, "other", custom, 2)], decision_revision: 2 };
      return route.fulfill({ json: value });
    });
    await page.goto(`/requests/${id}`);
    const clarification = page.getByRole("region", { name: t("Business clarification") });
    await clarification.getByRole("radio").last().check();
    await clarification.getByLabel(t("Describe your alternative rule"), { exact: true }).fill(custom);
    await clarification.getByRole("button", { name: t("Validate and continue"), exact: true }).click();
    const conflict = clarification.getByRole("region", { name: t("Review a changed decision") });
    await expect(conflict).toContainText(prior.value); await expect(conflict).toContainText(custom);
    expect(value.decisions[0].id).toBe(prior.id);
    await conflict.getByRole("button", { name: t("Confirm the change"), exact: true }).click();
    expect(calls).toHaveLength(2); expect(calls[1].confirm_changes).toBe(true);
    await expect(page.getByRole("heading", { name: t("Your request is queued"), exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: t("Confirmed business decisions") })).toContainText(custom);
  });

  test(`an explicitly selected latest result keeps its frozen decisions and stale results cannot be approved in ${language}`, async ({ page }) => {
    await setup(page, language);
    const first = decision(), changed = decision(rule, "block", undefined, 2);
    const frozen = version(1, [first]);
    const value: RequestDetail = { ...detail(), status: "READY", questions: [], decisions: [changed], decision_history: [first, changed], decision_revision: 2, latest_version: frozen, versions: [{ number: 1, status: "READY", created_at: timestamp }] };
    let validations = 0;
    await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: value }));
    await page.route(`**/api/requests/${id}/versions/1`, route => route.fulfill({ json: frozen }));
    await page.route(`**/api/requests/${id}/validation`, route => { validations++; return route.fulfill({ status: 409, json: { detail: "The result does not reflect the current decisions. Reanalyze before validation." } }); });
    await page.goto(`/requests/${id}`);
    const panel = page.getByRole("region", { name: t("Confirmed business decisions"), exact: true });
    await expect(panel).toContainText(changed.value);
    await expect(panel.getByRole("status")).toHaveText(t("The displayed result still uses earlier decisions. A new analysis must reflect your latest choices before validation."));
    await expect(panel.getByRole("button", { name: t("Validate business intent"), exact: true })).toHaveCount(0);
    await page.goto(`/requests/${id}?version=1`);
    await expect(panel).toContainText(first.value);
    await expect(panel.getByText(changed.value, { exact: true })).toHaveCount(0);
    await expect(panel.getByRole("button", { name: t("Revise decision"), exact: true })).toHaveCount(0);
    await expect(panel.getByRole("button", { name: t("Validate business intent"), exact: true })).toHaveCount(0);
    expect(validations).toBe(0);
  });

  test(`choice B retains its rule and resumes only its dependent clarification from the shared queue in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    let value = detail();
    const first = decision();
    const warning: ClarificationQuestion = { id: "warning", decision_key: "warning-message", kind: "free", question: "What should the warning tell the operations team?", reason: "This detail matters because you allowed cancellation with a warning." };
    let calls = 0;
    await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: value }));
    await page.route(`**/api/requests/${id}/answers`, async route => {
      calls++;
      if (calls === 1) {
        expect(route.request().postDataJSON()).toMatchObject({ choices: { cancellation: { option_id: "warn" } }, expected_decision_revision: 0 });
        value = { ...value, status: "QUEUED", questions: [], decisions: [first], decision_history: [first], decision_revision: 1 };
        await route.fulfill({ json: value });
        value = { ...value, status: "NEEDS_CLARIFICATION", questions: [warning] };
      } else {
        expect(route.request().postDataJSON()).toEqual({ answers: { warning: "Explain that benefit follow-up remains necessary." }, expected_decision_revision: 1 });
        value = { ...value, status: "QUEUED", questions: [] };
        await route.fulfill({ json: value });
      }
    });
    await page.route("**/api/queue", route => route.fulfill({ json: [{ id: 22, kind: "analysis", status: "DONE", queue_state: "PAUSED", title: "Cancellation clarification", environment_name: "Production", operation: "Analysis", assignment_state: "unassigned", request_status: "NEEDS_CLARIFICATION", stage: "Your answer is needed", pause_reason: "A business answer is needed.", created_at: timestamp, started_at: null, finished_at: timestamp, href: `/requests/${id}`, assignments: [], queue_position: null, error: "" }] }));
    await page.goto(`/requests/${id}`);
    await page.getByRole("region", { name: t("Business clarification") }).getByRole("radio").nth(1).check();
    await page.getByRole("button", { name: t("Validate and continue"), exact: true }).click();
    await expect(page.getByLabel(warning.question, { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: t("Business clarification") }).getByText(rule.question, { exact: true })).toHaveCount(0);
    await expect(page.getByRole("radio")).toHaveCount(0);
    await expect(page.getByRole("region", { name: t("Confirmed business decisions") })).toContainText(first.value);
    await page.goto("/");
    if (info.project.name === "mobile") await page.getByRole("button", { name: t("Task queue"), exact: true }).click();
    const queue = page.getByRole(info.project.name === "mobile" ? "dialog" : "complementary", { name: t("Task queue"), exact: true });
    await queue.getByRole("link", { name: /Cancellation clarification/ }).click();
    await expect(page.getByLabel(warning.question, { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: t("Confirmed business decisions") })).toContainText(first.value);
    await page.getByLabel(warning.question, { exact: true }).fill("Explain that benefit follow-up remains necessary.");
    await page.getByRole("button", { name: t("Answer and continue"), exact: true }).click();
    await expect(page.getByRole("heading", { name: t("Your request is queued"), exact: true })).toBeVisible();
    expect(calls).toBe(2);
  });

  for (const workflow of ["request", "question"] as const) test(`open ${workflow} clarification stays free and shows only established business context in ${language}`, async ({ page }) => {
    await setup(page, language);
    const base = workflow === "question" ? "questions" : "requests";
    let value: RequestDetail = { ...detail(workflow), questions: [{ id: "audience", question: "Who needs to understand this behavior?" }], business_summary: { desired: "Make cancellation understandable.", uncertainties: ["Current behavior has not been established."] } };
    await page.route(`**/api/${base}/${id}`, route => route.fulfill({ json: value }));
    await page.route(`**/api/${base}/${id}/answers`, route => {
      expect(route.request().postDataJSON()).toEqual({ answers: { audience: "The operations team" }, expected_decision_revision: 0 });
      value = { ...value, status: "QUEUED", questions: [] };
      return route.fulfill({ json: value });
    });
    await page.goto(`/${base}/${id}`);
    const clarification = page.getByRole("region", { name: t("Business clarification") });
    await expect(clarification.getByRole("radio")).toHaveCount(0);
    await expect(page.getByLabel(t("Compare multiple analyses"), { exact: true })).toHaveCount(0);
    const overview = page.getByRole("region", { name: t("Business overview") });
    await expect(overview.getByText(t("Current behavior"), { exact: true })).toHaveCount(0);
    await expect(overview.getByText(t("Gap to resolve"), { exact: true })).toHaveCount(0);
    await expect(overview).toContainText("Current behavior has not been established.");
    await clarification.getByLabel("Who needs to understand this behavior?", { exact: true }).fill("The operations team");
    await clarification.getByRole("button", { name: t("Answer and continue"), exact: true }).click();
    await expect(page.getByRole("heading", { name: t(workflow === "question" ? "Your question is queued" : "Your request is queued"), exact: true })).toBeVisible();
  });
}
