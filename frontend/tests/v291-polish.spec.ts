import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const id = "29292929-2929-4292-8292-292929292929";
const config = { reliability_protocol: "2.4", allow_same_family_fallback: true, max_calls: 12, global_instructions: "", verifier_enabled: true };
async function setup(page: Page, language: string) {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb" } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [], github: { status: "DISCONNECTED" } } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: config }));
  await page.route("**/api/ai-models?*", route => route.fulfill({ json: { items: [], discovery: { state: "unknown", reason: "not_refreshed" } } }));
  await page.route("**/api/analyses/overview", route => route.fulfill({ json: { sections: { clarify: { count: 0, items: [] }, consult: { count: 0, items: [] }, active: { count: 0, items: [] } }, recent: [] } }));
  await page.route("**/api/analyses?*", route => route.fulfill({ json: { items: [], total: 0, page: 1, pages: 0 } }));
}
function job(number: number, state: string, extra = {}) {
  const now = Date.now();
  return { id: number, kind: "analysis", request_id: String(number), workflow: "request", title: `Analysis ${number}`, status: state === "PAUSED" ? "DONE" : state,
    queue_state: state, request_status: state === "PAUSED" ? "NEEDS_CLARIFICATION" : state, environment_name: "Production", operation: "Analysis", href: `/analyses/${id}`,
    created_at: new Date(now - 14 * 3600000).toISOString(), started_at: new Date(now - 13 * 3600000 - 45000).toISOString(),
    finished_at: state === "PAUSED" ? new Date(now - 13 * 3600000 - 10000).toISOString() : null, error: "", ...extra };
}

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => (language === "en" ? en : fr)[key as keyof typeof en] || key;

  test(`queue attention survives navigation and shows separate waiting and active times in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    let jobs = [job(1, "PAUSED", { active_analysis_seconds: 35 }),
      job(2, "QUEUED", { started_at: null, queued_since: new Date(Date.now()-17*60000).toISOString() }),
      job(3, "RUNNING", { active_analysis_seconds: 43 }),
      job(30, "DONE", { request_id: "3", created_at: "2020-01-01T00:00:00Z" })];
    await page.route("**/api/queue", route => route.fulfill({ json: jobs }));
    await page.goto("/");
    const mobile = info.project.name === "mobile";
    await page.getByRole("button", { name: t("Activity"), exact: true }).click();
    const queue = page.getByRole(mobile ? "dialog" : "complementary", { name: t("Activity"), exact: true });
    await expect(queue.locator("[data-job]")).toHaveCount(3);
    await expect(queue.locator('[data-job="1"]')).toContainText(t("Waiting for your answer for {duration}").replace("{duration}", "13 h"));
    await expect(queue.locator("details")).toHaveCount(0);
    await expect(queue.locator('[data-job="1"]')).not.toContainText("35");
    await expect(queue.locator('[data-job="2"]')).toContainText(t("In queue for {duration}").replace("{duration}", "17 min"));
    await expect(queue.locator('[data-job="3"]')).toContainText(t("Active AI: {minutes}m {seconds}s").replace("{minutes}", "0").replace("{seconds}", "43"));
    await expect(queue).not.toContainText("Elapsed:");
    await expect(queue).not.toContainText("Requests, Questions");
    if (mobile) await page.keyboard.press("Escape");
    else {
      await page.getByRole("button", { name: t("Activity"), exact: true }).click();
      await expect(queue).toBeHidden();
    }
    jobs = [...jobs, job(4, "ERROR")];
    await page.evaluate(() => window.dispatchEvent(new Event("queue-updated")));
    await expect(page.locator("#activity-attention")).toContainText(t("One analysis needs your answer"));
    const toggle = page.getByRole("button", { name: t("Activity"), exact: true });
    await expect(toggle.locator(".queue-total")).toHaveText("2");
    await page.getByRole("navigation", { name: t("Main navigation"), exact: true }).getByRole("link", { name: t("Analyses"), exact: true }).click();
    await expect(page).toHaveURL(/\/analyses$/);
    if (!mobile) {
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await page.reload();
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
    }
    await toggle.click();
    await expect(queue.locator('[data-job="4"]')).toBeVisible();
    await queue.screenshot({ path: `../.local/v291-ui/queue-${language}-${info.project.name}.png`, animations: "disabled" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`quota age, thresholds and accessible details preserve known and unknown observations in ${language}`, async ({ page }) => {
    await setup(page, language);
    const now = new Date().toISOString();
    const values = [60, 59, 20, 19, 0, null].map((remaining, index) => ({ id: index+1, name: `Assistant ${index+1}`, agent: "codex", enabled: true, status: "CONNECTED", availability: remaining === 0 ? "QUOTA_EXHAUSTED" : "AVAILABLE",
      quota_windows: remaining === null ? {} : { session: { remaining_percent: remaining, observed_at: index === 0 ? "2020-01-01T00:00:00Z" : now, ...(index === 0 ? { reset_at: "2099-01-01T00:00:00Z" } : {}) } } }));
    await page.route("**/api/ai-connections", route => route.fulfill({ json: values }));
    let refreshes = 0;
    await page.route("**/api/ai-connections/*/quota/refresh", route => { refreshes++; return route.fulfill({ json: {} }); });
    const analysisCalls: string[] = [];
    page.on("request", request => { if (/\/(analyze|run)$/.test(request.url())) analysisCalls.push(request.url()); });
    await page.goto("/analyses");
    const sidebar = page.getByRole("complementary", { name: t("Instance navigation"), exact: true });
    for (const [id, color] of [[1,"green"],[2,"orange"],[3,"orange"],[4,"red"],[5,"red"]]) {
      await expect(sidebar.locator(`[data-connection="${id}"] [data-quota-color]`)).toHaveAttribute("data-quota-color", String(color));
      await expect(sidebar.locator(`[data-connection="${id}"] .connection-dot`)).toHaveCSS("background-color", color === "green" ? "rgb(21, 128, 61)" : color === "orange" ? "rgb(180, 83, 9)" : "rgb(185, 28, 28)");
    }
    const old = sidebar.locator('[data-connection="1"]');
    await expect(old.getByRole("link")).toHaveAccessibleName(new RegExp(t("Data needs refreshing")));
    await expect(old.locator("details")).toHaveCount(0);
    await expect(old.getByRole("link")).toHaveAttribute("href", "/admin?tab=ai-agents&connection=1");
    await expect(sidebar.locator('[data-connection="5"]')).toContainText(t("Quota exhausted"));
    await expect(sidebar.locator('[data-connection="6"]')).toContainText(t("Quota unknown"));
    await expect(sidebar.locator('[data-connection="6"] [role="meter"]')).toHaveCount(0);
    await sidebar.getByRole("button", { name: t("Refresh status and quotas"), exact: true }).click();
    await expect.poll(() => refreshes).toBe(6);
    expect(analysisCalls).toEqual([]);
  });

  test(`connection authentication, availability and quota stay distinct while advanced values persist in ${language}`, async ({ page }) => {
    await setup(page, language);
    let connection = { id: 1, name: "Team assistant", agent: "codex", enabled: true, status: "CONNECTED", availability: "QUOTA_EXHAUSTED", preference: 37, roles: ["verifier", "counter_analyst", "analyst"], quota_windows: { weekly: { remaining_percent: 0, observed_at: new Date().toISOString() } } };
    await page.route("**/api/ai-connections", route => route.fulfill({ json: [connection] }));
    let saved: Record<string, unknown> | undefined;
    await page.route("**/api/ai-connections/1", route => { saved = route.request().postDataJSON(); connection = { ...connection, ...saved }; return route.fulfill({ json: connection }); });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    const main = page.getByRole("main");
    await expect(main.getByText(t("Connected"), { exact: true }).first()).toBeVisible();
    const card = main.locator("#ai-connection-1");
    const quotaTag = card.getByText(t("Quota depleted"), { exact: true });
    await expect(quotaTag).toBeVisible();
    await expect(quotaTag).toHaveCSS("color", "rgb(255, 107, 125)");
    const quotaBox = (await quotaTag.boundingBox())!;
    const editBox = (await card.getByRole("button", { name: t("Edit"), exact: true }).boundingBox())!;
    expect(quotaBox.x + quotaBox.width).toBeLessThanOrEqual(editBox.x);
    await expect(card.getByText(t("Connection details"), { exact: true })).toHaveCount(0);
    await expect(card.getByText(t("Analysis roles"), { exact: true })).toHaveCount(0);
    await expect(card.locator(".connection-role-tag")).toHaveText([t("Analyst"), t("Counter-analyst"), t("Verifier")]);
    await expect(card.locator(".connection-role-tag").first()).toBeVisible();
    await card.locator(".connection-quotas > summary").click();
    await expect(card.locator(".connection-quotas").getByRole("progressbar")).toHaveJSProperty("value", 0);
    await expect(card.locator(".connection-quotas")).toContainText(t("0% remaining"));
    await main.getByLabel(t("More actions for {name}").replace("{name}", "Team assistant"), { exact: true }).click();
    await expect(main.getByRole("button", { name: t("Change account"), exact: true })).toBeVisible();
    await expect(main.getByRole("button", { name: t("Refresh status and quotas"), exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await main.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(page.getByLabel(t("Selection priority"), { exact: true })).toHaveCount(0);
    await expect(page.getByLabel(t("Participate in analyses"), { exact: true })).toHaveCount(0);
    await expect(main.locator("summary").filter({ hasText: t("Advanced options") })).toHaveCount(0);
    await expect(page.getByRole("group", { name: t("Analysis roles"), exact: true })).toBeVisible();
    await page.getByRole("group", { name: t("Analysis roles"), exact: true }).getByRole("checkbox", { name: t("Counter-analyst"), exact: true }).uncheck();
    await page.getByRole("group", { name: t("Analysis roles"), exact: true }).getByRole("checkbox", { name: t("Counter-analyst"), exact: true }).check();
    await page.getByRole("button", { name: t("Save"), exact: true }).click();
    await expect.poll(() => saved).toMatchObject({ preference: 37, enabled: true, roles: connection.roles });
    await expect(card.locator(".connection-role-tag")).toHaveText([t("Analyst"), t("Counter-analyst"), t("Verifier")]);
    await card.getByLabel(t("More actions for {name}").replace("{name}", "Team assistant"), { exact: true }).click();
    await card.getByRole("button", { name: t("Disable"), exact: true }).click();
    await expect(card.getByText(t("Disabled"), { exact: true })).toBeVisible();
    await card.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(page.getByRole("group", { name: t("Analysis roles"), exact: true }).getByRole("checkbox").first()).toBeEnabled();
    await page.getByRole("button", { name: t("Save"), exact: true }).click();
    await expect.poll(() => saved).toMatchObject({ preference: 37, enabled: false, roles: connection.roles });
    await page.getByRole("button", { name: t("Orchestration"), exact: true }).click();
    await expect(page.getByLabel(t("Maximum AI calls per analysis"), { exact: true })).toHaveCount(0);
    await expect(page.getByText(t("Automatic safeguards stop stalled or repeated steps and preserve completed observations."), { exact: true })).toBeVisible();
    await expect(page.getByLabel(t("Analysis time limit (seconds)"))).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`home and analysis cards distinguish partial results and keep full long titles accessible in ${language}`, async ({ page }) => {
    await setup(page, language);
    const title = "Contract cancellation and archived migration exceptions ".repeat(7);
    const item = { id, title, need: title + "\n" + "Detailed business context. ".repeat(30), href: `/analyses/${id}`, workflow: "question", intent_resolved: true,
      status: "PARTIAL", result_state: "partial", result_limits: ["Verifier quota unavailable."], environment_name: "Production", latest_activity_at: new Date().toISOString(), latest_version_number: 1 };
    await page.route("**/api/analyses/overview", route => route.fulfill({ json: { sections: { clarify: { count: 0, items: [] }, consult: { count: 1, items: [item] }, active: { count: 0, items: [] } }, recent: [item] } }));
    await page.route("**/api/analyses?*", route => route.fulfill({ json: { items: [item], total: 1, page: 1, pages: 1 } }));
    await page.goto("/");
    await expect(page.getByRole("heading", { name: t("Needs attention"), exact: true })).toBeVisible();
    const results = page.locator("section[aria-label]").filter({ has: page.getByRole("heading", { name: t("Results available"), exact: true }) });
    await expect(results).toContainText(t("Partial result"));
    await expect(results).not.toContainText("Verifier quota unavailable.");
    await page.getByRole("navigation", { name: t("Main navigation"), exact: true }).getByRole("link", { name: t("Analyses"), exact: true }).click();
    await expect(page.getByRole("button", { name: t("Search"), exact: true })).toBeVisible();
    const heading = page.getByRole("heading", { name: title, exact: true });
    await expect(heading).toHaveCSS("-webkit-line-clamp", "2");
    const link = page.getByRole("link").filter({ has: heading });
    await link.focus(); await expect(link).toBeFocused();
    await expect(link).toContainText(title);
    await expect(page.getByRole("navigation", { name: t("Main navigation"), exact: true }).getByRole("link")).toHaveText([t("Home"), t("Analyses"), t("Tickets")]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.local/v291-ui/list-${language}.png`, fullPage: true, animations: "disabled" });
  });

  test(`completed queue history stays bounded and partial work is never called complete in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const jobs = Array.from({ length: 9 }, (_, index) => job(index+1, "DONE", { request_status: "READY", finished_at: new Date(Date.now()-index*60000).toISOString(), analysis_state: index === 0 ? "partial" : "draft_ready", result_status: index === 0 ? "partial" : "complete", result_limits: index === 0 ? ["Verifier quota unavailable."] : [] }));
    await page.route("**/api/queue", route => route.fulfill({ json: jobs }));
    await page.goto("/analyses");
    await page.getByRole("button", { name: t("Activity"), exact: true }).click();
    const queue = page.getByRole(info.project.name === "mobile" ? "dialog" : "complementary", { name: t("Activity"), exact: true });
    await expect(queue.locator("[data-job]")).toHaveCount(0);
    await queue.getByRole("button", { name: t("Show recent completed activity"), exact: true }).click();
    await expect(queue.locator("[data-job]")).toHaveCount(5);
    await expect(queue.locator('[data-job="1"]')).toContainText(t("Partial result"));
    await expect(queue.locator('[data-job="1"]')).toHaveAttribute("data-result-status", "partial");
    await expect(queue.locator('[data-job="1"]')).not.toContainText(t("Complete result"));
    await expect(queue.locator('[data-job="1"]')).not.toContainText("Verifier quota unavailable.");
    await expect(queue.getByRole("link", { name: t("Activity history"), exact: true })).toHaveAttribute("href", "/analyses");
  });
}
