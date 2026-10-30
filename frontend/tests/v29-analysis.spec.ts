import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const id = "29292929-2929-4292-8292-292929292929";
const at = "2026-10-27T01:00:00Z";
function graph(invalid = false) {
  return { proposal: { id: "analyst:export", title: "Contract export", audience: "business", kind: "decision",
    purpose: "Explain the active contract filter.", alternative_text: "The export checks eligibility and includes active contracts. A future archived export is proposed.",
    nodes: [], edges: [{ id: "include", source: "request", target: "result", label: "Active contracts", meaning: "existing", claim_ids: ["analyst:export"] }] },
    reviews: [{ diagram_id: "analyst:export", edge_id: "include", verdict: "supported", notes: "Read the frozen selection guard." }],
    mermaid: invalid ? "invalid Mermaid fixture" : 'flowchart TD\n n0["Export request"]\n n1{"Eligibility"}\n n2["Active contracts"]\n n0 -->|"Existing — Check"| n1\n n1 -->|"Existing — Include"| n2' };
}
function dossier(invalid = false) {
  const evidence = { claims: [], database: { status: "not_configured", limitations: [], scope: "", checks: [] }, limitations: [], blocking: false, diagrams: [graph(invalid)] };
  const version = { id: "version", number: 1, status: "READY", format_version: "2.9", language: "en", created_at: at,
    explanation: { title: "Export behavior", summary: "Only active contracts are exported." },
    answer_markdown: "Only active contracts are exported.", markdown: "Only active contracts are exported.", goal_markdown: "", artifacts: {}, evidence, decisions_snapshot: [] };
  return { id, workflow: "question", intent_mode: "auto", need: "Explain the export.", original_need: "Explain the export.",
    title: "Export behavior", environment_id: 1, environment_name: "Staging", created_at: at, language: "en", status: "READY", confrontation: true,
    baseline: [], database: {}, questions: [], conversation: [], understanding: "Explain the export.", progress: [], error: "", attachments: [],
    latest_version: version, versions: [{ number: 1, status: "READY", created_at: at }], messages: [], ticket: null, markdown: null,
    decisions: [], decision_history: [], decision_revision: 0, validated_version: null, evidence,
    scope_assessment: null, scope_revision: 1, need_revision: 0, conclusions_stale: false, derived_requests: [] };
}
async function setup(page: Page, language: string) {
  await page.route("**/api/queue", route => route.fulfill({ json: [] }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb" } }));
  await page.route(`**/api/questions/${id}/versions/1/documents`, route => route.fulfill({ json: [] }));
}

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => (language === "en" ? en : fr)[key as keyof typeof en] || key;
  test(`unified analysis retains history and renders accessible diagrams in ${language}`, async ({ page }) => {
    test.setTimeout(60000);
    await setup(page, language);
    await page.route(`**/api/analyses/${id}`, route => route.fulfill({ json: dossier() }));
    await page.goto(`/analyses/${id}`);
    await expect(page.getByRole("link", { name: t("All analyses"), exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: t("Business conversation"), exact: true })).toContainText("Explain the export.");
    await page.getByRole("button", { name: t("Analysis report"), exact: true }).click();
    const diagram = page.locator("summary").filter({ hasText: /^Contract export$/ }).locator("..");
    await page.locator("summary").filter({ hasText: /^Contract export$/ }).click();
    await expect(diagram.getByRole("img")).toBeVisible();
    await expect(diagram.getByRole("img")).toHaveAttribute("alt", /eligibility/);
    await diagram.getByRole("button", { name: t("Zoom in"), exact: true }).click();
    await expect(diagram.getByRole("img")).toHaveAttribute("style", /125%/);
    await diagram.locator("summary").filter({ hasText: t("Mermaid source") }).click();
    await expect(diagram.locator("pre")).toContainText("flowchart TD");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("button", { name: t("Edit the need"), exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel(t("Updated need"), { exact: true })).toBeVisible();
    await page.getByLabel(t("Updated need"), { exact: true }).fill("Explain the archived export exception.");
    let saved = false;
    await page.route(`**/api/analyses/${id}/need`, route => {
      expect(route.request().postDataJSON()).toMatchObject({ need: "Explain the archived export exception.", expected_revision: 0, expected_version: 1, expected_decision_revision: 0 });
      saved = true;
      return route.fulfill({ json: { ...dossier(), status: "QUEUED", need_revision: 1, conclusions_stale: true, need: "Explain the archived export exception." } });
    });
    await page.getByRole("button", { name: t("Save and reanalyze"), exact: true }).click();
    await expect.poll(() => saved).toBe(true);
    await expect(page.getByText(t("Previous conclusions need reassessment"), { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Only active contracts are exported.", { exact: true }).first()).toBeVisible();
  });

  test(`invalid Mermaid retains readable business answer and source in ${language}`, async ({ page }) => {
    await setup(page, language);
    await page.route(`**/api/analyses/${id}`, route => route.fulfill({ json: dossier(true) }));
    await page.goto(`/analyses/${id}`);
    await page.getByRole("button", { name: t("Analysis report"), exact: true }).click();
    await page.locator("summary").filter({ hasText: /^Contract export$/ }).click();
    await expect(page.getByText(t("The diagram could not be rendered. Its explanation and Mermaid source remain available."), { exact: true })).toBeVisible();
    await expect(page.locator("pre").filter({ hasText: "invalid Mermaid fixture" })).toBeVisible();
    await expect(page.getByText("Only active contracts are exported.", { exact: true }).first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`canonical historical question URL waits for its workflow before loading the chosen version in ${language}`, async ({ page }) => {
    await setup(page, language);
    const old = { ...dossier().latest_version, evidence: {}, explanation: { title: "Historical export", summary: "The historical export had an explicit limit." },
      answer_markdown: "The historical export had an explicit limit.", markdown: "The historical export had an explicit limit." };
    const current = { ...dossier().latest_version, number: 2, evidence: {} };
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route(`**/api/analyses/${id}`, async route => { await gate; return route.fulfill({ json: { ...dossier(), latest_version: current, versions: [
      { number: 1, created_at: at, status: "READY" }, { number: 2, created_at: at, status: "READY" },
    ] } }); });
    const wrongWorkflow: string[] = [];
    await page.route(`**/api/requests/${id}/versions/*`, route => { wrongWorkflow.push(route.request().url()); return route.fulfill({ status: 404 }); });
    await page.route(`**/api/questions/${id}/versions/1`, route => route.fulfill({ json: old }));
    await page.goto(`/analyses/${id}?version=1`);
    await expect(page.getByText(t("Loading analysis…"), { exact: true })).toBeVisible();
    release();
    await page.getByRole("button", { name: t("Analysis report"), exact: true }).click();
    await expect(page.getByLabel(t("Result version"), { exact: true })).toHaveValue("1");
    await expect(page.getByText("The historical export had an explicit limit.", { exact: true }).first()).toBeVisible();
    expect(wrongWorkflow).toEqual([]);
  });

  test(`home links to creation of one untyped analysis with attachments in ${language}`, async ({ page }) => {
    await setup(page, language);
    await page.route("**/api/settings", route => route.fulfill({ json: { name: "Acme Assistant", language, primary_color: "#2563eb" } }));
    await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Staging", status: "READY", repositories: [] }] }));
    await page.route("**/api/analyses/overview", route => route.fulfill({ json: { sections: {
      clarify: { count: 0, items: [] }, consult: { count: 0, items: [] }, active: { count: 0, items: [] },
    }, recent: [] } }));
    let created: Record<string, unknown> | undefined;
    let analyses = 0, uploads = 0;
    let saved = { ...dossier(), workflow: "request", status: "DRAFT", latest_version: null, versions: [], ticket: null };
    await page.route("**/api/analyses", route => { created = route.request().postDataJSON(); return route.fulfill({ status: 201, json: saved }); });
    await page.route(`**/api/analyses/${id}`, route => route.fulfill({ json: saved }));
    await page.route(`**/api/analyses/${id}/attachments`, route => { uploads++; return route.fulfill({ status: 201, json: { id: "attachment" } }); });
    await page.route(`**/api/analyses/${id}/analyze`, route => { analyses++; saved = { ...saved, status: "QUEUED" }; return route.fulfill({ json: saved }); });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Acme Assistant", exact: true })).toBeVisible();
    await expect(page.locator(".home-hero h1 svg")).toHaveCount(1);
    await expect(page.locator(".home-eyebrow")).toHaveCount(0);
    await expect(page.getByText(t("Welcome back to SpecHelper!"), { exact: true })).toHaveCount(0);
    await expect(page.getByLabel(t("Your question or change"), { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: t("New analysis"), exact: true }).click();
    await expect(page).toHaveURL(/\/analyses\?new=1&from_home=1$/);
    await page.getByLabel(t("Environment"), { exact: true }).selectOption("1");
    await page.getByLabel(t("Your question or change"), { exact: true }).fill("Explain the export and how to improve it.");
    await page.locator('input[type="file"]').setInputFiles({ name: "context.md", mimeType: "text/markdown", buffer: Buffer.from("Export context") });
    await page.getByRole("button", { name: t("Start discussion"), exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/analyses/${id}$`));
    expect(created).toEqual({ environment_id: 1, need: "Explain the export and how to improve it." });
    expect(uploads).toBe(1); expect(analyses).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`analysis search filters and pagination retain actual server state in ${language}`, async ({ page }) => {
    await setup(page, language);
    await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Staging", status: "READY", repositories: [] }] }));
    const requests: URLSearchParams[] = [];
    await page.route("**/api/analyses?*", route => {
      const parameters = new URL(route.request().url()).searchParams; requests.push(parameters);
      const second = parameters.get("page") === "2";
      return route.fulfill({ json: { items: [{ ...dossier(), title: second ? "Second result" : "Historical question", intent_resolved: true,
        href: `/analyses/${id}`, latest_activity_at: at, latest_version_number: 1 }], total: 21, page: second ? 2 : 1, pages: 2, has_previous: second, has_next: !second } });
    });
    await page.goto("/analyses");
    await page.getByLabel(t("Search analyses"), { exact: true }).fill("export");
    await page.getByRole("button", { name: t("Search"), exact: true }).click();
    await page.getByRole("button", { name: t("Questions"), exact: true }).click();
    await page.getByLabel(t("Environment"), { exact: true }).selectOption("1");
    await page.getByLabel(t("Status"), { exact: true }).selectOption("READY");
    await page.getByRole("button", { name: t("Next"), exact: true }).click();
    await expect(page.getByRole("heading", { name: "Second result", exact: true })).toBeVisible();
    expect(Object.fromEntries(requests.at(-1)!)).toMatchObject({ q: "export", workflow: "question", environment_id: "1", status: "READY", page: "2" });
    await page.getByRole("button", { name: t("Previous"), exact: true }).click();
    await expect(page.getByRole("heading", { name: "Historical question", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`historical question prepares a sourced linked evolution without rewriting its answer in ${language}`, async ({ page }) => {
    await setup(page, language);
    const childId = "29292929-2929-4292-8292-292929292930";
    const parent = { ...dossier(), evidence: {}, latest_version: { ...dossier().latest_version, evidence: {} } };
    await page.route(`**/api/questions/${id}`, route => route.fulfill({ json: parent }));
    await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Staging", status: "READY", repositories: [] }] }));
    await page.route("**/api/analyses/overview", route => route.fulfill({ json: { sections: {
      clarify: { count: 0, items: [] }, consult: { count: 1, items: [] }, active: { count: 0, items: [] },
    }, recent: [] } }));
    await page.route(`**/api/questions/${id}/versions/1/transfer`, route => route.fulfill({ json: {
      name: "source-question.md", content: "Original sourced answer with its limits.", source_question_id: id, source_version: 1,
      summary: "Only active contracts are exported.", result_status: "PARTIAL", environment_id: 1, baseline: [], language,
    } }));
    const child = { ...dossier(), id: childId, workflow: "request", status: "DRAFT", latest_version: null, versions: [], ticket: null };
    let submitted: Record<string, unknown> | undefined;
    const operationIds = new Set<string>();
    let attempts = 0;
    await page.route(`**/api/questions/${id}/requests`, route => {
      submitted = route.request().postDataJSON(); operationIds.add(String(submitted?.operation_id));
      if (++attempts === 1) return route.abort("failed");
      return route.fulfill({ status: 201, json: child });
    });
    await page.route(`**/api/analyses/${childId}`, route => route.fulfill({ json: child }));
    await page.route(`**/api/analyses/${childId}/analyze`, route => route.fulfill({ json: { ...child, status: "QUEUED" } }));
    await page.goto(`/questions/${id}`);
    await page.getByRole("link", { name: t("Prepare a change"), exact: true }).click();
    await expect(page.getByText(t("Partial source answer: its conclusions still have verification limits."), { exact: true })).toBeVisible();
    await expect(page.getByLabel(t("Your requested change"), { exact: true })).toHaveValue("");
    await page.getByLabel(t("Your requested change"), { exact: true }).fill("Add an explicit archived-contract export option.");
    await page.getByRole("button", { name: t("Launch deep analysis"), exact: true }).click();
    await expect(page.getByRole("alert").first()).toBeVisible();
    await page.reload();
    await expect(page.getByLabel(t("Your requested change"), { exact: true })).toHaveValue("Add an explicit archived-contract export option.");
    await page.getByRole("button", { name: t("Launch deep analysis"), exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/analyses/${childId}$`));
    expect(submitted).toMatchObject({ source_version: 1, environment_id: 1, include_context: true, need: "Add an explicit archived-contract export option." });
    expect(submitted?.operation_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(attempts).toBe(2); expect(operationIds.size).toBe(1);
    expect(parent.latest_version.explanation.summary).toBe("Only active contracts are exported.");
  });
}
