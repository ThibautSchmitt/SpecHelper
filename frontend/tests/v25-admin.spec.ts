import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const translate = (language: "en" | "fr", key: string) => (language === "en" ? en : fr)[key as keyof typeof en] || key;
async function setup(page: Page, language: "en" | "fr") {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb", short_label: "", allow_confrontation: true } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4", global_instructions: "State evidence limits.", global_instruction_version: 1, allow_confrontation: true, verifier_enabled: true, allow_same_family_fallback: true, max_calls: 12, tool_timeout_seconds: 300 } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [], github: { status: "DISCONNECTED" } } }));
  await page.route("**/api/ai-models*", route => route.fulfill({ json: { items: [], discovery: { state: "unknown", reason: "not_refreshed" } } }));
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "en" ? "light" : "dark");
}
const assistant = (id: number, remaining?: number, extra = {}) => ({ id, name: `Assistant ${id}`, agent: id % 2 ? "codex" : "claude", enabled: true, status: "CONNECTED", availability: "AVAILABLE", identity_id: `identity-${id}`, account: "", quota_status: { state: remaining === undefined ? "unavailable" : "available", checked_at: new Date().toISOString() }, quota_windows: remaining === undefined ? {} : { session: { used_percent: 100 - remaining, observed_at: new Date().toISOString() } }, ...extra });

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(language, key);
  test(`sidebar remaining quotas, limiting window and unknown states in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const values = [assistant(1, 15), assistant(2, 45), assistant(3, 85), assistant(4), assistant(5, 0, { availability: "QUOTA_EXHAUSTED" }), assistant(6, 90, { status: "DISCONNECTED" }), assistant(7, 60), assistant(8, 80, { quota_windows: { session: { used_percent: 20, observed_at: new Date().toISOString() }, weekly: { used_percent: 90, observed_at: new Date().toISOString() } } })];
    values.push(assistant(9, 85, { availability: "QUOTA_EXHAUSTED", quota_windows: { session: { used_percent: 15, observed_at: new Date().toISOString() }, weekly: { exhausted: true } } }));
    await page.route("**/api/ai-connections", route => route.fulfill({ json: values }));
    let gitReads = 0;
    await page.route("**/api/git-connections", route => { gitReads += 1; return route.fulfill({ json: [] }); });
    await page.goto("/questions");
    const sidebar = page.getByRole("complementary", { name: t("Instance navigation"), exact: true });
    for (const [id, percent, color] of [[1,15,"red"],[2,45,"orange"],[3,85,"green"],[5,0,"red"],[7,60,"green"],[8,10,"red"]] as const) {
      const card = sidebar.locator(`[data-connection="${id}"]`);
      await expect(card.locator('[role="meter"]')).toHaveAttribute("aria-valuenow", String(percent));
      await expect(card.locator("[data-quota-color]")).toHaveAttribute("data-quota-color", color);
    }
    await expect(sidebar.locator('[data-connection="4"]')).toContainText(t("Quota unknown"));
    await expect(sidebar.locator('[data-connection="4"] [role="meter"]')).toHaveCount(0);
    await expect(sidebar.locator('[data-connection="6"]')).toContainText(t("Authentication required"));
    await expect(sidebar.locator('[data-connection="6"] [role="meter"]')).toHaveCount(0);
    await expect(sidebar.locator('[data-connection="5"]')).toContainText(t("Quota exhausted"));
    await expect(sidebar.locator('[data-connection="9"]')).toContainText(t("Quota exhausted"));
    await expect(sidebar.locator('[data-connection="9"] [role="meter"]')).toHaveCount(0);
    await expect(sidebar.getByText(t("Sources Git"), { exact: true })).toHaveCount(0);
    expect(gitReads).toBe(0);
    await expect(sidebar.locator('[data-provider="codex"]').first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (info.project.name === "desktop") await sidebar.screenshot({ path: `../.local/v25-ui/sidebar-${language}.png`, animations: "disabled" });
  });

  test(`quota refresh uses metadata, retains stale observations offline and preserves navigation in ${language}`, async ({ page }) => {
    await setup(page, language);
    let offline = false;
    let refreshes = 0;
    const values = [assistant(1, 45, { quota_identity_id: "shared" }), assistant(2, 45, { quota_identity_id: "shared" })];
    await page.route("**/api/ai-connections", route => offline ? route.abort() : route.fulfill({ json: values }));
    await page.route("**/api/ai-connections/*/quota/refresh", route => { refreshes += 1; offline = true; return route.fulfill({ json: { quota_refresh_state: "error" } }); });
    const analysisCalls: string[] = [];
    page.on("request", request => { if (/\/(?:analyze|run)$/.test(request.url())) analysisCalls.push(request.url()); });
    await page.goto("/questions");
    const sidebar = page.getByRole("complementary", { name: t("Instance navigation"), exact: true });
    await expect(sidebar.locator('[data-connection="1"] [role="meter"]')).toHaveAttribute("aria-valuenow", "45");
    await sidebar.getByRole("button", { name: t("Refresh status and quotas"), exact: true }).click();
    await expect(sidebar.getByRole("status")).toContainText(t("Refresh unavailable; previous observations retained"));
    await expect(sidebar.locator('[data-connection="1"] [data-stale]')).toHaveAttribute("data-stale", "true");
    await expect(sidebar.locator('[data-connection="1"] [role="meter"]')).toHaveAttribute("aria-valuenow", "45");
    expect(refreshes).toBe(1);
    expect(analysisCalls).toEqual([]);
    await expect(sidebar.getByRole("link", { name: t("Settings"), exact: true })).toBeVisible();
  });

  test(`skill authoring has global adapters and calculated capabilities in ${language}`, async ({ page }) => {
    await setup(page, language);
    await page.route("**/api/ai-connections", route => route.fulfill({ json: [] }));
    let saved: Record<string, unknown> | null = null;
    await page.route("**/api/library/skill", route => {
      if (route.request().method() === "POST") saved = route.request().postDataJSON();
      return route.fulfill({ json: [] });
    });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    await page.getByRole("button", { name: t("Skills"), exact: true }).click();
    await page.getByRole("button", { name: t("New skill"), exact: true }).click();
    await expect(page.getByRole("group", { name: t("Compatible assistants"), exact: true })).toHaveCount(0);
    await expect(page.getByRole("group", { name: t("Required capabilities"), exact: true })).toHaveCount(0);
    await expect(page.getByLabel(t("Calculated skill metadata"), { exact: true })).toContainText("ChatGPT / Codex, Claude Code");
    await page.getByLabel(t("Identifier"), { exact: true }).fill("rare-counts");
    await page.getByLabel(t("Name"), { exact: true }).fill("Rare counts");
    await page.getByLabel(t("Objective"), { exact: true }).fill("Find population exceptions.");
    await page.getByLabel(t("Instructions"), { exact: true }).fill("Inspect PostgreSQL populations with bounded read-only counts.");
    await page.getByRole("button", { name: t("Save definition"), exact: true }).click();
    await expect.poll(() => saved).toMatchObject({ compatibility: [], required_capabilities: [], enabled: true });
  });

  test(`periodic quota refresh groups identities and skips active assistants in ${language}`, async ({ page }) => {
    await setup(page, language);
    await page.clock.install();
    const values = [assistant(1, 85, { quota_identity_id: "shared" }), assistant(2, 85, { quota_identity_id: "shared" }), assistant(3, 45, { availability: "BUSY" })];
    await page.route("**/api/ai-connections", route => route.fulfill({ json: values }));
    const refreshed: string[] = [];
    await page.route("**/api/ai-connections/*/quota/refresh", route => { refreshed.push(route.request().url()); return route.fulfill({ json: { quota_refresh_state: "refreshed" } }); });
    await page.goto("/questions");
    await expect(page.locator('[data-connection="1"] [role="meter"]')).toHaveCount(1);
    expect(refreshed).toEqual([]);
    await page.clock.fastForward(120001);
    await expect.poll(() => refreshed.length).toBe(1);
    expect(refreshed[0]).toMatch(/\/ai-connections\/1\/quota\/refresh$/);
  });

  test(`model catalog precedes secondary manual authoring in ${language}`, async ({ page }) => {
    await setup(page, language);
    await page.route("**/api/ai-connections", route => route.fulfill({ json: [] }));
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    await page.getByRole("button", { name: t("Models"), exact: true }).click();
    await expect(page.getByLabel(t("Model identifier"), { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: t("Refresh models"), exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Add a documented model"), exact: true }).click();
    await expect(page.getByLabel(t("Model identifier"), { exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Cancel"), exact: true }).click();
    await expect(page.getByLabel(t("Model identifier"), { exact: true })).toHaveCount(0);
  });
}
