import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import type { LibraryDefinition } from "../src/components/ai-library";
import type { QueueJob } from "../src/components/task-queue";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const id = "24242424-2424-4242-8242-242424242424";
const stamp = "2026-10-24T10:00:00Z";
const translation = (language: "en" | "fr", key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
const config = { reliability_protocol: "2.4", global_instructions: "Cite decisive source evidence.", global_instruction_version: 4, allow_confrontation: true, verifier_enabled: true, allow_same_family_fallback: true, max_calls: 12, tool_timeout_seconds: 120 };
async function setup(page: Page, language: "en" | "fr") {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, short_label: "", primary_color: "#2563eb", allow_confrontation: true } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { github: { status: "CONNECTED" }, ais: [], databases: [] } }));
  await page.route("**/api/ai-connections", route => route.fulfill({ json: [{ id: 1, name: "ChatGPT team", agent: "codex", model: "", status: "CONNECTED", availability: "AVAILABLE", enabled: true, is_default: true, preference: 100, roles: ["analyst", "counter_analyst", "verifier"], additional_instructions: "Inspect exact caller paths.", skill_overrides: { historical: false } }] }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: config }));
  await page.route("**/api/ai-models*", route => route.fulfill({ json: { items: [], discovery: { state: "unknown", reason: "not_refreshed" } } }));
  await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Production", status: "READY", repositories: [], revision: 1 }] }));
  await page.route("**/api/environments/1/context", route => route.fulfill({ json: { instructions: "A closed contract is archived.", instructions_enabled: true, revision: 1, resources: [], max_files: 20, max_file_size: 26214400 } }));
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "fr" ? "dark" : "light");
}
function skill(slug: string, name: string): LibraryDefinition {
  return { slug, name, objective: `Review ${name.toLowerCase()} boundaries.`, instructions: "Inspect the current source and record limits.", enabled: true, compatibility: [], required_capabilities: ["read_sources"], version: 1, deleted: false, expected_checks: [] };
}
async function queuePanel(page: Page, language: "en" | "fr", mobile: boolean) {
  const t = (key: string) => translation(language, key);
  if (mobile) await page.getByRole("button", { name: t("Task queue"), exact: true }).click();
  return page.getByRole(mobile ? "dialog" : "complementary", { name: t("Task queue"), exact: true });
}
for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translation(language, key);
  test(`role coverage distinguishes missing assignments from quota waits in ${language}`, async ({ page }) => {
    await setup(page, language);
    let coverage = { complete: false, roles: { analyst: { configured: [1], available: [1] }, counter_analyst: { configured: [] as number[], available: [] as number[] }, verifier: { configured: [] as number[], available: [] as number[] } } };
    await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { ...config, role_coverage: coverage } }));
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    await page.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(page.getByLabel(t("Default connection when available"), { exact: true })).toHaveCount(0);
    const roles = page.getByRole("group", { name: t("Analysis roles"), exact: true });
    await page.getByLabel(t("Participate in analyses"), { exact: true }).uncheck();
    for (const input of await roles.getByRole("checkbox").all()) await expect(input).toBeDisabled();
    await page.getByLabel(t("Participate in analyses"), { exact: true }).check();
    for (const input of await roles.getByRole("checkbox").all()) await expect(input).toBeChecked();
    await page.getByRole("navigation", { name: t("AI settings"), exact: true }).getByRole("button", { name: t("Roles and orchestration"), exact: true }).click();
    const panel = page.getByRole("region", { name: t("Role coverage"), exact: true });
    await expect(panel).toContainText(t("Configuration incomplete"));
    await expect(panel.getByText(t("Not covered"), { exact: true })).toHaveCount(2);
    coverage = { complete: true, roles: { analyst: { configured: [1], available: [] }, counter_analyst: { configured: [1], available: [] }, verifier: { configured: [1], available: [] } } };
    await page.evaluate(() => window.dispatchEvent(new Event("connections-updated")));
    await expect(panel).toContainText(t("Configuration complete"));
    await expect(panel.getByText(t("Covered · waiting for availability"), { exact: true })).toHaveCount(3);
  });
  test(`two instruction levels and factual environment settings in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    let instructions = config.global_instructions;
    const writes: Record<string, unknown>[] = [];
    await page.route("**/api/orchestration-settings", route => {
      if (route.request().method() === "PUT") { const body = route.request().postDataJSON(); writes.push(body); instructions = body.global_instructions ?? instructions; }
      return route.fulfill({ json: { ...config, global_instructions: instructions } });
    });
    let connectionWrite: Record<string, unknown> | null = null;
    await page.route("**/api/ai-connections/1", route => { connectionWrite = route.request().postDataJSON(); return route.fulfill({ json: { id: 1, ...connectionWrite } }); });
    const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
    await page.goto("/admin");
    await page.getByLabel(t("Global instructions"), { exact: true }).fill("Record facts, exceptions and unanswered decisions.");
    await page.getByRole("button", { name: t("Save global instructions"), exact: true }).click();
    await expect.poll(() => writes[0]).toEqual({ global_instructions: "Record facts, exceptions and unanswered decisions." });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `../.local/v24-ui/global-${language}-${info.project.name}.png`, fullPage: true, animations: "disabled" });
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    const nav = page.getByRole("navigation", { name: t("AI settings"), exact: true });
    await expect(nav.getByRole("button", { name: t("Agents"), exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: t("Edit"), exact: true }).click();
    await page.getByText(t("Specific instructions"), { exact: true }).first().click();
    await page.getByLabel(t("Specific instructions"), { exact: true }).fill("Check callers before generalizing.");
    await expect(page.locator("[id^=ai-skill-]")).toHaveCount(0);
    await page.getByRole("button", { name: t("Save connection"), exact: true }).click();
    await expect.poll(() => connectionWrite).toMatchObject({ additional_instructions: "Check callers before generalizing.", roles: ["analyst", "counter_analyst", "verifier"] });
    expect(connectionWrite).not.toHaveProperty("skill_overrides");
    await nav.getByRole("button", { name: t("Roles and orchestration"), exact: true }).click();
    await expect(page.getByText(t("Independent review is required"), { exact: true })).toBeVisible();
    await expect(page.getByLabel(t("Analysis time limit (seconds)"), { exact: true })).toHaveCount(0);
    await expect(page.locator("[id^=role-instructions-]")).toHaveCount(0);
    await expect(page.getByText(t("Default skills"), { exact: true })).toHaveCount(0);
    await page.locator("summary").filter({ hasText: t("Advanced options") }).click();
    await page.getByLabel(t("Maximum AI calls per analysis"), { exact: true }).fill("14");
    await page.getByRole("button", { name: t("Save analysis settings"), exact: true }).click();
    await expect.poll(() => writes[1]).toEqual({ allow_same_family_fallback: true, max_calls: 14 });
    await page.getByRole("button", { name: t("Sources & environments"), exact: true }).click();
    await page.getByRole("button", { name: t("Environments"), exact: true }).click();
    await expect(page.getByText(t("Agents and skills for this environment"), { exact: true })).toHaveCount(0);
    await page.getByText(t("Environment context"), { exact: true }).click();
    await expect(page.getByLabel(t("Business terminology and factual context"), { exact: true })).toHaveValue("A closed contract is archived.");
    await expect(page.getByLabel(t("Short environment instructions"), { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.local/v24-ui/settings-${language}-${info.project.name}.png`, fullPage: true });
  });

  test(`global skills retain search, history, editing and activation in ${language}`, async ({ page }) => {
    await setup(page, language);
    let items = [skill("billing", "Billing review"), skill("stock", "Stock review")];
    const original = structuredClone(items[0]);
    await page.route("**/api/library/skill", route => route.fulfill({ json: items }));
    await page.route("**/api/library/skill/billing/versions", route => route.fulfill({ json: [{ version: 1, action: "created", definition: original, editor: "administrator", created_at: stamp }] }));
    await page.route(/\/api\/library\/skill\/billing(?:\?.*)?$/, route => {
      if (route.request().method() === "DELETE") { items = items.filter(item => item.slug !== "billing"); return route.fulfill({ json: { deleted: true } }); }
      const body = route.request().postDataJSON();
      const next = { ...items[0], ...body, version: body.expected_version + 1 };
      items = [next, items[1]]; return route.fulfill({ json: next });
    });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    await page.getByRole("button", { name: t("Skills"), exact: true }).click();
    await expect(page.getByRole("button", { name: t("Generate a skill"), exact: true })).toBeVisible();
    await page.getByLabel(t("Search skills"), { exact: true }).fill("billing");
    await expect(page.getByRole("heading", { name: /Billing review/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Stock review/ })).toHaveCount(0);
    await page.getByRole("button", { name: t("Edit {name}").replace("{name}", "Billing review"), exact: true }).click();
    await expect(page.getByRole("group", { name: t("Required skills"), exact: true })).toHaveCount(0);
    await page.getByLabel(t("Instructions"), { exact: true }).fill("Inspect billing boundaries and rare states.");
    await page.getByRole("button", { name: t("Save skill"), exact: true }).click();
    await expect(page.getByRole("heading", { name: /Billing review/ })).toContainText("v2");
    await page.getByRole("button", { name: t("Versions of {name}").replace("{name}", "Billing review"), exact: true }).click();
    await page.locator("summary").filter({ hasText: /^v1/ }).click();
    await expect(page.locator("details").filter({ has: page.locator("summary", { hasText: /^v1/ }) })).toContainText(original.instructions);
    await page.getByRole("button", { name: t("Deactivate {name}").replace("{name}", "Billing review"), exact: true }).click();
    await expect(page.getByRole("button", { name: t("Activate {name}").replace("{name}", "Billing review"), exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Delete {name}").replace("{name}", "Billing review"), exact: true }).click();
    await page.getByRole("group", { name: t("Confirm deletion"), exact: true }).getByRole("button", { name: t("Confirm deletion"), exact: true }).click();
    await expect(page.getByRole("heading", { name: /Billing review v/ })).toHaveCount(0);
    await page.getByLabel(t("Search skills"), { exact: true }).fill("");
    await expect(page.getByRole("heading", { name: /Stock review/ })).toBeVisible();
  });

  test(`parallel jobs keep roles, genuine time, waiting and cancellation in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const job = (number: number, state: string, role = "analyst", agent = "codex"): QueueJob => ({ id: number, kind: "analysis", workflow: "request", title: `Export boundaries ${number}`, request_id: number === 1 ? id : id.slice(0, -12) + String(number).padStart(12, "0"), status: state === "PAUSED" ? "DONE" : state === "WAITING_AI" ? "QUEUED" : state, queue_state: state, request_status: state === "PAUSED" ? "NEEDS_CLARIFICATION" : state, environment_name: `Environment ${number}`, operation: "Source analysis", public_role: role, stage_number: role === "verifier" ? 3 : role === "counter_analyst" ? 2 : 1, stage_count: 3, active_analysis_seconds: state === "RUNNING" ? 367 : 0, agent, assignments: [{ connection_id: number, connection_name: agent === "codex" ? "ChatGPT team" : "Claude team", agent, model: "recorded-model", public_role: role }], assignment_state: state === "RUNNING" ? "current" : "previous", created_at: stamp, started_at: stamp, finished_at: null, queue_position: null, error: "", can_cancel: number === 1, href: `/requests/${id}`, waiting_reason: state === "WAITING_AI" ? "Waiting for an eligible connection from a different model family." : "", pause_reason: state === "PAUSED" ? "A business answer is needed." : "" });
    let values = [job(1, "RUNNING"), job(2, "RUNNING", "counter_analyst", "claude"), job(3, "WAITING_AI", "verifier"), job(4, "PAUSED"), job(5, "CANCELLED")];
    await page.route("**/api/queue", route => route.fulfill({ json: values }));
    let cancellations = 0;
    await page.route(`**/api/requests/${id}/cancel`, route => { cancellations += 1; values = values.map(item => item.id === 1 ? { ...item, status: "CANCELLED", queue_state: "CANCELLED", request_status: "CANCELLED", can_cancel: false } : item); return route.fulfill({ json: { status: "CANCELLED" } }); });
    await page.goto("/questions");
    const panel = await queuePanel(page, language, info.project.name === "mobile");
    await expect(panel.locator('[data-state="RUNNING"][data-job]')).toHaveCount(2);
    await expect(panel.locator('[data-job="1"]')).toContainText(t("Active AI: {minutes}m {seconds}s").replace("{minutes}", "6").replace("{seconds}", "7"));
    await expect(panel.locator('[data-job="1"]')).toContainText(t("Step {step} of {total}").replace("{step}", "1").replace("{total}", "3"));
    await expect(panel.locator('[data-job="2"]')).toContainText(t("Counter-analyst"));
    await expect(panel.locator('[data-job="2"] [data-provider="claude"]')).toBeVisible();
    await expect(panel.locator('[data-job="3"]')).toContainText(t("Waiting for AI"));
    await expect(panel.locator('[data-job="3"]')).toContainText(t("Waiting for an eligible connection from a different model family."));
    await expect(panel.locator('[data-job="4"]')).toContainText(t("Your answer is needed"));
    await expect(panel.locator('[data-job="5"]')).toContainText(t("Cancelled"));
    await expect(panel.getByText(/\d+%/)).toHaveCount(0);
    await panel.locator('[data-job="1"]').getByRole("button", { name: t("Cancel analysis: {title}").replace("{title}", "Export boundaries 1"), exact: true }).click();
    await expect.poll(() => cancellations).toBe(1);
    await expect(panel.locator('[data-job="1"]')).toHaveAttribute("data-state", "CANCELLED");
    await expect(panel.locator('[data-job="2"]')).toHaveAttribute("data-state", "RUNNING");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect.poll(async () => panel.locator("[data-job]").evaluateAll(cards => cards.slice(1).every((card, index) => card.getBoundingClientRect().top >= cards[index].getBoundingClientRect().bottom - 1))).toBe(true);
    await panel.evaluate(node => { node.scrollTop = 0; });
    await panel.screenshot({ path: `../.local/v24-ui/queue-${language}-${info.project.name}.png`, animations: "disabled" });
  });
}
