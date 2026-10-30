import { test, expect } from "./fixtures";
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
for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(language, key);
  test(`diagram annex is opt-in and previewed without agent calls in ${language}`, async ({ page }) => {
    await setup(page, language);
    await publications(page, false, false, false, true);
    let submitted: Record<string, unknown> | undefined;
    const analyses: string[] = [];
    page.on("request", request => { if (/\/(analyze|continue)$/.test(request.url())) analyses.push(request.url()); });
    await page.route(`**${endpoint}/publications`, route => {
      if (route.request().method() === "GET") return route.fulfill({ json: [] });
      submitted = route.request().postDataJSON();
      return route.fulfill({ json: { id: "diagram-publication", status: "PUBLISHED", external_id: "123", attachment_delivery: [{ id: "diagrams", name: "diagrams.md", status: "TRANSFERRED" }] } });
    });
    await page.goto(`/requests/${id}`);
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await expect(dialog.getByLabel(t("Include attachments"), { exact: true })).not.toBeChecked();
    await dialog.getByLabel(t("Include attachments"), { exact: true }).check();
    await expect(dialog.getByLabel(/^diagrams.md/)).not.toBeChecked();
    await dialog.getByLabel(/^diagrams.md/).check();
    await expect(dialog.getByLabel(t("Attachment transfer preview"), { exact: true })).toContainText("diagrams.md");
    await expect(dialog.getByLabel(t("Ticket description"), { exact: true })).not.toHaveValue(/mermaid/);
    await dialog.getByRole("button", { name: t("Create ticket"), exact: true }).click();
    await expect.poll(() => submitted).toMatchObject({ include_attachments: true, include_diagrams: true, include_goal: false, attachment_ids: [], confirmed: true });
    expect(analyses).toEqual([]);
  });
  for (const workflow of ["request", "question"] as const) test(`free ${workflow} entry and compact accessible file validation in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const base = workflow === "question" ? "questions" : "analyses";
    let created: Record<string, unknown> | undefined;
    await page.route(`**/api/${base}`, route => {
      if (route.request().method() === "POST") { created = route.request().postDataJSON(); return route.fulfill({ json: { id } }); }
      return route.fulfill({ json: [] });
    });
    await page.route(`**/api/${base}/${id}/analyze`, route => route.fulfill({ json: { status: "QUEUED" } }));
    await page.route(`**/api/${base}/${id}`, route => route.fulfill({ json: { ...detail(), workflow, status: "QUEUED", latest_version: null, ticket: null } }));
    await page.goto(workflow === "request" ? "/analyses?new=1" : "/questions");
    await expect(page.getByRole("group", { name: t(workflow === "question" ? "Question type" : "Request type"), exact: true })).toHaveCount(0);
    await page.getByLabel(t("Environment"), { exact: true }).selectOption("1");
    await page.getByLabel(t(workflow === "question" ? "Your question" : "Your question or change"), { exact: true }).fill("How does mobile validation work?");
    await page.locator("#attachments").setInputFiles({ name: "invalid.exe", mimeType: "application/octet-stream", buffer: Buffer.from("content") });
    await expect(page.locator(".file-selection").getByRole("alert")).toContainText(t("One of the file formats is not allowed."));
    await expect(page.locator(".file-selection")).toContainText("1 KB");
    await page.getByRole("button", { name: t("Remove file {name}").replace("{name}", "invalid.exe"), exact: true }).click();
    const drop = await page.evaluateHandle(() => { const data = new DataTransfer(); data.items.add(new File(["reference"], "reference.md", { type: "text/markdown" })); return data; });
    await page.locator("#create-work-item form").dispatchEvent("drop", { dataTransfer: drop });
    await expect(page.locator(".file-selection")).toContainText("reference.md");
    await page.getByRole("button", { name: t("Remove file {name}").replace("{name}", "reference.md"), exact: true }).click();
    expect(await page.locator('[data-dragging]').evaluate(node => node.getBoundingClientRect().height)).toBeLessThan(120);
    await page.screenshot({ path: `../.local/v25-ui/form-${workflow}-${language}-${info.project.name}.png`, fullPage: true });
    await page.getByRole("button", { name: t(workflow === "question" ? "Analyze question" : "Start analysis"), exact: true }).click();
    await expect.poll(() => created).toMatchObject({ environment_id: 1, need: "How does mobile validation work?" });
    expect(created).not.toHaveProperty("category");
    await expect(page).toHaveURL(new RegExp(`/${base}/${id}$`));
  });
  test(`one activity card per request, partial result and collapsed completion in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const job = (number: number, status: string, target: string, created = stamp) => ({ id: number, kind: "analysis", workflow: "request", title: `Validation ${target}`, request_id: target, status, queue_state: status, request_status: status === "DONE" ? "PARTIAL" : "ANALYZING", result_status: status === "DONE" ? "partial" : "pending", result_limits: status === "DONE" ? ["Verifier quota unavailable."] : [], environment_name: "Production", operation: "Analysis", agent: "codex", assignments: [{ connection_id: 1, connection_name: "ChatGPT", agent: "codex", model: "observed-model", public_role: "verifier" }], public_role: "verifier", stage_number: 3, stage_count: 3, elapsed_seconds: 147, created_at: created, finished_at: status === "DONE" ? stamp : null, href: `/requests/${target}`, error: "", queue_position: null });
    await page.route("**/api/queue", route => route.fulfill({ json: [job(1, "DONE", id, "2026-10-23T03:00:00Z"), job(2, "DONE", id, "2026-10-23T04:00:00Z"), job(3, "DONE", id), job(4, "RUNNING", "active-request"), { ...job(5, "DONE", "sync"), kind: "sync", request_id: null, title: "Successful Git sync" }] }));
    await page.goto("/questions");
    if (info.project.name === "mobile") await page.getByRole("button", { name: t("Task queue"), exact: true }).click();
    const panel = page.getByRole(info.project.name === "mobile" ? "dialog" : "complementary", { name: t("Task queue"), exact: true });
    await expect(panel.locator("[data-job]")).toHaveCount(1);
    await expect(panel.getByRole("button", { name: `${t("Completed")} (1)`, exact: true })).toHaveAttribute("aria-expanded", "false");
    await panel.getByRole("button", { name: `${t("Completed")} (1)`, exact: true }).click();
    await expect(panel.locator("[data-job]")).toHaveCount(2);
    await expect(panel.locator('[data-job="3"]')).toContainText(t("Partial result"));
    await expect(panel.locator('[data-job="3"]')).toContainText("Verifier quota unavailable.");
    await expect(panel.getByText("Successful Git sync")).toHaveCount(0);
    await expect(panel.locator('[data-job="4"]')).toContainText(t("Step {step} of {total}").replace("{step}", "3").replace("{total}", "3"));
    await expect(panel.getByText(/\d+%/)).toHaveCount(0);
    await panel.screenshot({ path: `../.local/v25-ui/queue-${language}-${info.project.name}.png`, animations: "disabled" });
  });
  test(`real template choices, standard sections, required fields and persisted edits in ${language}`, async ({ page }, info) => {
    await setup(page, language); const fixture = await publications(page, false, true);
    const analysisCalls: string[] = []; page.on("request", request => { if (/\/(analyze|continue)$/.test(request.url())) analysisCalls.push(request.url()); });
    await page.goto(`/requests/${id}`);
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await expect(dialog.getByLabel(t("Ticket template"), { exact: true }).locator("option")).toHaveCount(3);
    await dialog.getByLabel(t("Ticket template"), { exact: true }).selectOption("feature");
    await expect(dialog.getByLabel(t("Ticket description"), { exact: true })).toHaveValue(/Short verified feature description/);
    await dialog.getByLabel(t("Ticket format"), { exact: true }).selectOption("standard");
    await expect(dialog.getByLabel(t("Ticket description"), { exact: true })).toHaveValue(/## Business summary/);
    await expect(dialog.getByLabel(t("Ticket description"), { exact: true })).not.toHaveValue(/Detailed business analysis/);
    await dialog.getByLabel(t("Include detailed business analysis"), { exact: true }).check();
    await expect(dialog.getByLabel(t("Ticket description"), { exact: true })).toHaveValue(/## Detailed business analysis/);
    await dialog.getByLabel(t("Include detailed technical analysis"), { exact: true }).check();
    await expect(dialog.getByLabel(t("Ticket description"), { exact: true })).toHaveValue(/## Detailed technical analysis/);
    await dialog.getByLabel(t("Include detailed business analysis"), { exact: true }).uncheck();
    await dialog.getByLabel(t("Include detailed technical analysis"), { exact: true }).uncheck();
    await expect(dialog.getByLabel(t("Ticket description"), { exact: true })).not.toHaveValue(/## Detailed/);
    await expect(dialog.locator(".markdown-preview")).toContainText("spechelper:draft-1");
    await expect(dialog.getByRole("button", { name: t("Create ticket"), exact: true })).toBeDisabled();
    await expect(dialog.getByText(t("Complete the required field: {field}.").replace("{field}", "Owning team"), { exact: true })).toBeVisible();
    await expect(dialog.getByText(t("Complete the required field: {field}.").replace("{field}", "Delivery date"), { exact: true })).toBeVisible();
    await dialog.getByLabel("Owning team", { exact: false }).selectOption("billing");
    await dialog.getByLabel("Delivery date", { exact: false }).fill("2026-11-01");
    await expect(dialog.getByRole("button", { name: t("Create ticket"), exact: true })).toBeEnabled();
    await dialog.getByLabel(t("Ticket title"), { exact: true }).fill("Reviewed title");
    await dialog.getByRole("button", { name: t("Save publication draft"), exact: true }).click();
    await expect(dialog.getByText(t("Publication draft saved."), { exact: true })).toBeVisible();
    await dialog.getByRole("button", { name: t("Close"), exact: true }).click();
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await expect(dialog.getByLabel(t("Ticket title"), { exact: true })).toHaveValue("Reviewed title");
    await expect(dialog.getByLabel("Owning team", { exact: false })).toHaveValue("billing");
    await expect(dialog.getByLabel(t("Include attachments"), { exact: true })).not.toBeChecked();
    expect(fixture.value.latest_version.goal_markdown).toContain("EXHAUSTIVE_GOAL_UNCHANGED");
    expect(analysisCalls).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await dialog.screenshot({ path: `../.local/v25-ui/ticket-${language}-${info.project.name}.png`, animations: "disabled" });
  });
  test(`missing project templates fall back explicitly without hiding required destination fields in ${language}`, async ({ page }) => {
    await setup(page, language); await publications(page, false, true, false);
    await page.goto(`/requests/${id}`); await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await expect(dialog.getByLabel(t("Ticket format"), { exact: true })).toHaveValue("standard");
    await expect(dialog.getByLabel(t("Ticket format"), { exact: true }).locator('option[value="project"]')).toBeDisabled();
    await expect(dialog.getByText(t("This project exposes no usable ticket template. The standard SpecHelper format is selected; required destination fields still apply."), { exact: true })).toBeVisible();
    await expect(dialog.getByLabel("Owning team", { exact: false })).toBeVisible();
    await expect(dialog.getByRole("button", { name: t("Create ticket"), exact: true })).toBeDisabled();
  });
  test(`explicit attachment consent, separate goal and exact publication payload in ${language}`, async ({ page }) => {
    await setup(page, language); await publications(page);
    let payload: Record<string, unknown> | undefined;
    await page.route(`**${endpoint}/publications`, route => { if (route.request().method() === "GET") return route.fulfill({ json: [] }); payload = route.request().postDataJSON(); return route.fulfill({ json: { id: "publication-1", status: "PUBLISHED", external_id: "123", attachment_delivery: [{ id: "original-1", name: "screen.png", status: "TRANSFERRED" }, { id: "goal", name: "goal.md", status: "UNCERTAIN", error: "Upload interrupted." }] } }); });
    await page.goto(`/requests/${id}`); await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await expect(dialog.getByLabel(t("Include attachments"), { exact: true })).not.toBeChecked();
    await expect(dialog.getByLabel(t("Attachment transfer preview"), { exact: true })).toContainText(t("None"));
    await dialog.getByLabel(t("Include attachments"), { exact: true }).check();
    await expect(dialog.getByText(t("Selected files will be sent to {destination}.").replace("{destination}", "Team project"), { exact: true })).toBeVisible();
    await expect(dialog.getByLabel(/oversized.pdf/)).toBeDisabled();
    await dialog.getByLabel(/screen.png/).check();
    await dialog.getByLabel(/^goal.md/).check();
    await expect(dialog.getByLabel(t("Attachment transfer preview"), { exact: true })).toContainText("screen.png, goal.md");
    await dialog.getByRole("button", { name: t("Create ticket"), exact: true }).click();
    await expect.poll(() => payload).toMatchObject({ include_attachments: true, attachment_ids: ["original-1"], include_goal: true, draft_id: "draft-1", title: "Fix mobile validation", fields: {}, confirmed: true });
    await expect(dialog.getByLabel(t("Attachment transfer results"), { exact: true })).toContainText(t("File transfer outcome unknown"));
    await expect(dialog.getByLabel(t("Attachment transfer results"), { exact: true })).toContainText(t("Check the destination before transferring this file again."));
  });
  test(`unchecked files never enter the publication consent in ${language}`, async ({ page }) => {
    await setup(page, language); await publications(page);
    let payload: Record<string, unknown> | undefined;
    await page.route(`**${endpoint}/publications`, route => {
      if (route.request().method() === "GET") return route.fulfill({ json: [] });
      payload = route.request().postDataJSON(); return route.fulfill({ json: { id: "publication-1", status: "PUBLISHED", external_id: "123" } });
    });
    await page.goto(`/requests/${id}`); await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await dialog.getByLabel(t("Include attachments"), { exact: true }).check();
    await dialog.getByLabel(/screen.png/).check();
    await dialog.getByLabel(t("Include attachments"), { exact: true }).uncheck();
    await expect(dialog.getByLabel(t("Attachment transfer preview"), { exact: true })).toContainText(t("None"));
    await dialog.getByRole("button", { name: t("Create ticket"), exact: true }).click();
    await expect.poll(() => payload).toMatchObject({ include_attachments: false, attachment_ids: [], include_goal: false });
  });
  test(`uncertain publication recovery reuses the exact reviewed consent in ${language}`, async ({ page }) => {
    await setup(page, language); await publications(page);
    const posted: Record<string, unknown>[] = [];
    await page.route(`**${endpoint}/publications`, route => {
      if (route.request().method() === "GET") return route.fulfill({ json: posted.length ? [{ id: "publication-1", status: "UNCERTAIN", connector_id: 1, project: "TEAM", idempotency_key: posted[0].idempotency_key, snapshot: posted[0] }] : [] });
      posted.push(route.request().postDataJSON());
      return route.fulfill({ json: posted.length === 1 ? { id: "publication-1", status: "UNCERTAIN" } : { id: "publication-1", status: "PUBLISHED", external_id: "123", url: "https://tickets.example.test/123" } });
    });
    await page.goto(`/requests/${id}`); await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    let dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await dialog.getByLabel(t("Ticket title"), { exact: true }).fill("Exact reviewed title");
    await dialog.getByRole("button", { name: t("Create ticket"), exact: true }).click();
    await expect(dialog.getByRole("button", { name: t("Verify publication"), exact: true })).toBeVisible();
    await dialog.getByRole("button", { name: t("Close"), exact: true }).click();
    await page.reload(); await page.evaluate(() => sessionStorage.clear());
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByRole("button", { name: t("Verify publication"), exact: true }).click();
    await expect(dialog.getByRole("link", { name: t("Open ticket"), exact: true })).toHaveAttribute("href", "https://tickets.example.test/123");
    expect(posted).toHaveLength(2); expect(posted[1]).toEqual(posted[0]);
  });
  test(`a conflicting saved draft can be reloaded without overwriting another browser in ${language}`, async ({ page }) => {
    await setup(page, language); await publications(page);
    let writes = 0;
    await page.route(`**${endpoint}/publication-draft?*`, route => {
      if (route.request().method() !== "PUT") return route.fallback();
      writes++; return route.fulfill({ status: 409, json: { detail: "The ticket draft changed. Reload it before saving your edits." } });
    });
    await page.goto(`/requests/${id}`); await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await dialog.getByLabel(t("Ticket title"), { exact: true }).fill("Unsaved local edit");
    await dialog.getByRole("button", { name: t("Save publication draft"), exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText(t("The ticket draft changed. Reload it before saving your edits."));
    await expect(dialog.getByLabel(t("Ticket title"), { exact: true })).toHaveValue("Unsaved local edit");
    await expect(dialog.getByRole("button", { name: t("Close without saving"), exact: true })).toBeVisible();
    page.once("dialog", value => value.accept());
    await dialog.getByRole("button", { name: t("Reload saved draft"), exact: true }).click();
    await expect(dialog.getByLabel(t("Ticket title"), { exact: true })).toHaveValue("Fix mobile validation");
    await expect(dialog.getByRole("alert")).toHaveCount(0);
    expect(writes).toBe(1);
    await dialog.getByRole("button", { name: t("Close"), exact: true }).click();
    await expect(dialog).not.toBeVisible();
  });
  test(`partial verification keeps draft and artifacts visible but cannot publish in ${language}`, async ({ page }) => {
    await setup(page, language); const fixture = await publications(page, true);
    let posts = 0; page.on("request", request => { if (request.url().endsWith("/publications") && request.method() === "POST") posts++; });
    await page.goto(`/requests/${id}`);
    await expect(page.getByLabel(t("Result reliability"), { exact: true })).toContainText("Verifier quota unavailable.");
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await expect(dialog.getByText(t("Publication is blocked"), { exact: true })).toBeVisible();
    await expect(dialog.getByRole("button", { name: t("Create ticket"), exact: true })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: t("Create ticket"), exact: true })).toHaveAccessibleDescription(/Verifier quota unavailable/);
    await dialog.getByLabel(t("Ticket title"), { exact: true }).fill("Consultable partial draft");
    await dialog.getByRole("button", { name: t("Cancel"), exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect.poll(() => fixture.saves.length).toBe(1);
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    await dialog.getByLabel(t("Publication connection"), { exact: true }).selectOption("1");
    await expect(dialog.getByLabel(t("Ticket title"), { exact: true })).toHaveValue("Consultable partial draft");
    expect(posts).toBe(0); expect(fixture.value.latest_version.status).toBe("PARTIAL");
  });
}
