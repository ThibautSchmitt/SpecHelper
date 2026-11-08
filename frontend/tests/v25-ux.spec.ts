import { test, expect, openAnalysisReport } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const id = "25252525-2525-4252-8252-252525252525";
const stamp = "2026-10-24T04:00:00Z";
const endpoint = `/api/requests/${id}/versions/1`;
const translate = (language: "en" | "fr", key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
async function setup(page: Page, language: "en" | "fr") {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb" } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { github: { status: "CONNECTED" }, ais: [], databases: [] } }));
  await page.route("**/api/analyses/overview", route => route.fulfill({ json: { sections: { clarify: { count: 0, items: [] }, consult: { count: 0, items: [] }, active: { count: 0, items: [] } }, recent: [] } }));
  await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Production", status: "READY", repositories: [], revision: 1 }] }));
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "fr" ? "dark" : "light");
}
function detail(partial = false) {
  const version = { id: "version-1", number: 1, format_version: "1.2", language: "en", status: partial ? "PARTIAL" : "READY", created_at: stamp, ticket: { title: "Fix mobile validation", context: "Retain the verified baseline.", need: "Validate on mobile.", proposed_solution: "Use the existing guard." }, markdown: "# Frozen ticket", goal_markdown: "# EXHAUSTIVE_GOAL_UNCHANGED", artifacts: {}, evidence: { blocking: partial, database: { status: "not_configured", scope: "", limitations: [], checks: [] }, claims: [], limitations: partial ? ["Verifier quota unavailable."] : [] } };
  return { id, workflow: "request", analysis_protocol: "2.4", need: "Fix mobile validation", status: version.status, language: "en", environment_id: 1, environment_name: "Production", created_at: stamp, confrontation: true, baseline: [{ repository: "app", branch: "main", sha: "a".repeat(40) }], database: {}, questions: [], conversation: [], progress: [], understanding: "Validate on mobile", error: "", attachments: [], ticket: version.ticket, markdown: version.markdown, versions: [{ number: 1, status: version.status, created_at: stamp }], latest_version: version, messages: [] };
}
const files = [
  { id: "original-1", name: "screen.png", size: 8192, mime: "image/png", kind: "original", transferable: true },
  { id: "goal", name: "goal.md", size: 4096, mime: "text/markdown", kind: "goal", transferable: true },
  { id: "blocked-1", name: "oversized.pdf", size: 100000000, mime: "application/pdf", kind: "original", transferable: false, reason: "This connector cannot transfer this file." },
];
async function publications(page: Page, partial = false, required = false, hasTemplates = true, hasDiagrams = false) {
  const value = detail(partial);
  await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: value }));
  await page.route(`**${endpoint}/publications`, route => route.request().method() === "GET" ? route.fulfill({ json: [] }) : route.fulfill({ json: { id: "publication-1", status: "PUBLISHED", external_id: "123", url: "https://tickets.example.test/123", attachment_delivery: [] } }));
  await page.route(`**/api/ticket-connectors?request_id=${id}`, route => route.fulfill({ json: [{ id: 1, name: "Team Jira", platform: "jira", status: "CONNECTED", projects: ["TEAM"], default_project: "TEAM" }] }));
  await page.route("**/api/ticket-connectors/1/projects", route => route.fulfill({ json: [{ id: "TEAM", name: "Team project" }] }));
  let state = { ticket_format: hasTemplates ? "project" : "standard", template_id: hasTemplates ? "bug" : "", issue_type: "task", include_business_analysis: false, include_technical_analysis: false, include_attachments: false, attachment_ids: [] as string[], include_goal: false, include_diagrams: false };
  const available = hasDiagrams ? [...files, { id: "diagrams", name: "diagrams.md", size: 1024, mime: "text/plain", kind: "diagrams", transferable: true }] : files;
  let title = "Fix mobile validation";
  let body = "## Bug\n\nShort verified bug description.";
  let fields: Record<string, unknown> = required ? { team: "", due: "" } : {};
  let revision = 1;
  const reads: unknown[] = [];
  const saves: Record<string, unknown>[] = [];
  const response = () => ({ ...state, draft_id: "draft-1", draft_revision: revision, title, body, fields: required ? [{ id: "team", label: "Owning team", type: "select", required: true, options: [{ id: "billing", name: "Billing" }] }, { id: "due", label: "Delivery date", type: "text", required: true, options: [] }] : [], values: fields, labels: [], assignees: [], defaults: { labels: [], assignees: [] }, templates: hasTemplates ? [{ id: "bug", name: "Bug" }, { id: "feature", name: "Feature" }] : [], fallback_reason: hasTemplates ? "" : "This project exposes no usable ticket template. The standard SpecHelper format is selected; required destination fields still apply.", issue_types: [{ id: "task", name: "Task" }], revision: "metadata-1", format: "markdown", publication_reference: "spechelper:draft-1", available_attachments: available, selected_attachments: state.include_attachments ? available.filter(file => file.transferable && (file.kind === "goal" ? state.include_goal : file.kind === "diagrams" ? state.include_diagrams : state.attachment_ids.includes(file.id))) : [], publication_allowed: !partial, publication_blockers: partial ? ["Verifier quota unavailable."] : [], version_id: "version-1", environment_name: "Production", baseline: value.baseline });
  await page.route(`**${endpoint}/publication-draft?*`, route => {
    if (route.request().method() === "PUT") {
      const payload = route.request().postDataJSON(); saves.push(payload); title = payload.title; body = payload.body; fields = payload.fields; revision++;
    }
    return route.fulfill({ json: response() });
  });
  await page.route(`**${endpoint}/publication-preview`, route => {
    const payload = route.request().postDataJSON(); reads.push(payload); state = { ...state, ...payload };
    body = state.ticket_format === "standard" ? "## Title\nFix mobile validation\n\n## Description\nShort change.\n\n## Business summary\nFewer failures.\n\n## Technical summary\nReuse guard.\n\n## Proposed solution\nValidate before saving." : state.template_id === "feature" ? "## Feature\n\nShort verified feature description." : "## Bug\n\nShort verified bug description.";
    if (state.include_business_analysis) body += "\n\n## Detailed business analysis\nBusiness detail.";
    if (state.include_technical_analysis) body += "\n\n## Detailed technical analysis\nTechnical detail.";
    revision++; return route.fulfill({ json: response() });
  });
  return { value, reads, saves };
}
// Historical result publication remains readable; editing and conflict coverage
// lives in conversation-ticket-preparation.spec.ts, using the active draft API.
for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(language, key);
  async function openPublication(page: Page) {
    await page.goto(`/requests/${id}`);
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    return dialog;
  }
  test(`historical diagrams are opt-in and publication requires confirmation in ${language}`, async ({ page }) => {
    await setup(page, language); await publications(page, false, false, false, true);
    let submitted: Record<string, unknown> | undefined;
    const analyses: string[] = [];
    page.on("request", request => { if (/\/(analyze|continue)$/.test(request.url())) analyses.push(request.url()); });
    await page.route(`**${endpoint}/publications`, route => {
      if (route.request().method() === "GET") return route.fulfill({ json: [] });
      submitted = route.request().postDataJSON();
      return route.fulfill({ json: { id: "diagram-publication", status: "PUBLISHED", external_id: "123", url: "https://tickets.example.test/123", attachment_delivery: [] } });
    });
    const dialog = await openPublication(page);
    const attachments = dialog.getByRole("checkbox", { name: new RegExp(t("Include attachments")) });
    await expect(attachments).not.toBeChecked();
    await attachments.check();
    await expect(dialog.getByRole("checkbox", { name: /^diagrams.md/ })).not.toBeChecked();
    await dialog.getByRole("checkbox", { name: /^diagrams.md/ }).check();
    await dialog.getByRole("button", { name: t("Publish"), exact: true }).click();
    expect(submitted).toBeUndefined();
    await dialog.getByRole("alertdialog").getByRole("button", { name: t("Confirm publication"), exact: true }).click();
    await expect.poll(() => submitted).toMatchObject({ include_attachments: true, include_diagrams: true, include_goal: false, attachment_ids: [], confirmed: true });
    expect(analyses).toEqual([]);
  });

  test(`historical preview uses Markdown and keeps required provider fields in ${language}`, async ({ page }) => {
    await setup(page, language); const fixture = await publications(page, false, true);
    const dialog = await openPublication(page);
    await expect(dialog.getByLabel(t("Ticket template"), { exact: true }).locator("option")).toHaveCount(3);
    await dialog.getByLabel(t("Ticket template"), { exact: true }).selectOption("feature");
    await expect(dialog).toContainText("Short verified feature description.");
    await expect(dialog.getByRole("button", { name: t("Publish"), exact: true })).toBeDisabled();
    await dialog.getByLabel("Owning team", { exact: false }).selectOption("billing");
    await dialog.getByLabel("Delivery date", { exact: false }).fill("2026-11-01");
    await expect(dialog.getByRole("button", { name: t("Publish"), exact: true })).toBeEnabled();
    await expect(dialog).not.toContainText("spechelper:draft-1");
    await expect(dialog.getByRole("textbox", { name: t("Ticket description"), exact: true })).toHaveCount(0);
    expect(fixture.value.latest_version.goal_markdown).toContain("EXHAUSTIVE_GOAL_UNCHANGED");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`missing historical templates do not hide required destination fields in ${language}`, async ({ page }) => {
    await setup(page, language); await publications(page, false, true, false);
    const dialog = await openPublication(page);
    await expect(dialog.getByLabel(t("Ticket format"), { exact: true })).toHaveCount(0);
    await expect(dialog.getByLabel("Owning team", { exact: false })).toBeVisible();
    await expect(dialog.getByRole("button", { name: t("Publish"), exact: true })).toBeDisabled();
  });

  test(`unchecked files never enter the historical publication consent in ${language}`, async ({ page }) => {
    await setup(page, language); await publications(page);
    let payload: Record<string, unknown> | undefined;
    await page.route(`**${endpoint}/publications`, route => {
      if (route.request().method() === "GET") return route.fulfill({ json: [] });
      payload = route.request().postDataJSON();
      return route.fulfill({ json: { id: "publication-1", status: "PUBLISHED", external_id: "123", url: "https://tickets.example.test/123" } });
    });
    const dialog = await openPublication(page);
    const attachments = dialog.getByRole("checkbox", { name: new RegExp(t("Include attachments")) });
    await attachments.check();
    await dialog.getByRole("checkbox", { name: /^screen.png/ }).check();
    await expect(dialog.getByRole("checkbox", { name: /^oversized.pdf/ })).toBeDisabled();
    await attachments.uncheck();
    await dialog.getByRole("button", { name: t("Publish"), exact: true }).click();
    expect(payload).toBeUndefined();
    await dialog.getByRole("alertdialog").getByRole("button", { name: t("Confirm publication"), exact: true }).click();
    await expect.poll(() => payload).toMatchObject({ include_attachments: false, attachment_ids: [], include_goal: false, confirmed: true });
  });

  test(`uncertain historical publication recovery preserves exact reviewed consent in ${language}`, async ({ page }) => {
    await setup(page, language); await publications(page);
    const posted: Record<string, unknown>[] = [];
    await page.route(`**${endpoint}/publications`, route => {
      if (route.request().method() === "GET") return route.fulfill({ json: posted.length ? [{ id: "publication-1", status: "UNCERTAIN", connector_id: 1, project: "TEAM", idempotency_key: posted[0].idempotency_key, snapshot: posted[0] }] : [] });
      posted.push(route.request().postDataJSON());
      return route.fulfill({ json: posted.length === 1 ? { id: "publication-1", status: "UNCERTAIN" } : { id: "publication-1", status: "PUBLISHED", external_id: "123", url: "https://tickets.example.test/123" } });
    });
    let dialog = await openPublication(page);
    await dialog.getByRole("button", { name: t("Publish"), exact: true }).click();
    await dialog.getByRole("alertdialog").getByRole("button", { name: t("Confirm publication"), exact: true }).click();
    await expect(dialog.getByRole("button", { name: t("Verify publication"), exact: true })).toBeVisible();
    await dialog.getByRole("button", { name: t("Back"), exact: true }).click();
    await page.reload(); await page.evaluate(() => sessionStorage.clear());
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByRole("button", { name: t("Verify publication"), exact: true }).click();
    await expect(dialog.getByRole("link", { name: t("Open ticket"), exact: true })).toHaveAttribute("href", "https://tickets.example.test/123");
    expect(posted).toHaveLength(2);
    const { draft_id, draft_revision, ...consent } = posted[0];
    expect(draft_id).toBe("draft-1"); expect(draft_revision).toBeGreaterThan(0);
    expect(posted[1]).toEqual(consent);
  });

  test(`partial historical results preserve limits and never claim complete verification in ${language}`, async ({ page }) => {
    await setup(page, language); const fixture = await publications(page, true);
    let posts = 0;
    page.on("request", request => { if (request.url().endsWith("/publications") && request.method() === "POST") posts++; });
    await page.goto(`/requests/${id}`); await openAnalysisReport(page);
    await expect(page.getByLabel(t("Result reliability"), { exact: true })).toContainText("Verifier quota unavailable.");
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await expect(dialog.getByText(t("Publication is blocked"), { exact: true })).toBeVisible();
    await expect(dialog.getByRole("button", { name: t("Publish"), exact: true })).toBeDisabled();
    expect(posts).toBe(0); expect(fixture.value.latest_version.status).toBe("PARTIAL");
  });
}
