import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import { translate, type Language } from "../src/lib/i18n";

async function setup(page: Page, language: Language) {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { authenticated: true, mode: "local" } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { language, name: "SpecHelper", primary_color: "#2563eb" } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [] } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4" } }));
  await page.route("**/api/analyses/overview", route => route.fulfill({ json: { sections: { clarify: { count: 0, items: [] }, consult: { count: 0, items: [] }, active: { count: 0, items: [] } }, recent: [] } }));
  await page.route("**/api/analyses?*", route => route.fulfill({ json: { items: [], total: 0, page: 1, pages: 0 } }));
}

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(key, language);

  test(`known resets refresh a shared identity once and update settings in ${language}`, async ({ page }) => {
    await page.clock.install({ time: new Date("2026-10-27T10:00:00Z") });
    await setup(page, language);
    const observed = "2026-10-27T10:00:00Z";
    let values = [1, 2].map(id => ({ id, agent: "codex", name: `Shared ${id}`, enabled: true, status: "CONNECTED", availability: "AVAILABLE", quota_identity_id: "shared", quota_status: { state: "available", checked_at: observed }, quota_windows: {
      session: { remaining_percent: 0, exhausted: true, observed_at: observed, resets_at: "2026-10-27T10:00:30Z" },
    } }));
    await page.route("**/api/ai-connections", route => route.fulfill({ json: values }));
    let refreshes = 0;
    await page.route("**/api/ai-connections/*/quota/refresh", route => {
      refreshes++;
      values = values.map(value => ({ ...value, quota_windows: { session: { remaining_percent: 90, exhausted: false, observed_at: "2026-10-27T10:00:31Z", resets_at: "2026-10-27T15:00:00Z" } } }));
      return route.fulfill({ json: { quota_refresh_state: "refreshed" } });
    });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    const window = page.getByRole("main").locator('[data-quota-window="session"]');
    await expect(window).toContainText(t("Quota exhausted"));
    await page.clock.fastForward(31000);
    await expect.poll(() => refreshes).toBe(1);
    await expect(window).toContainText(/90\s*%/);
  });

  test(`all quota windows preserve dates, credits and unknown states in ${language}`, async ({ page }) => {
    await setup(page, language);
    const now = new Date().toISOString();
    const reset = "2030-01-07T09:00:00Z";
    const connections = [{ id: 1, agent: "codex", name: "Known account", enabled: true, status: "CONNECTED", availability: "AVAILABLE", quota_identity_id: "one", quota_status: { state: "available", checked_at: now }, quota_windows: {
      session: { remaining_percent: 76, observed_at: now, window_minutes: 300, source: "codex_app_server" },
      weekly: { remaining_percent: 24, observed_at: "2020-01-01T00:00:00Z", resets_at: reset },
      credits: { remaining_units: 7.5, observed_at: now, unit: "credits" },
      "limit:model:daily": { remaining_percent: 0, scope: "provider_limit", limit_id: "model", observed_at: now },
    } }, { id: 2, agent: "antigravity", name: "Unknown account", enabled: true, status: "CONNECTED", availability: "AVAILABLE", quota_identity_id: "two", quota_status: { state: "unavailable" }, quota_windows: {} }];
    await page.route("**/api/ai-connections", route => route.fulfill({ json: connections }));
    let refreshes = 0;
    await page.route("**/api/ai-connections/*/quota/refresh", route => { refreshes++; return route.fulfill({ json: {} }); });
    const inference: string[] = [];
    page.on("request", request => { if (/\/(run|analyze)$/.test(request.url())) inference.push(request.url()); });
    await page.goto("/admin");
    const sidebar = page.locator('[data-connection="1"]');
    await expect(sidebar.locator('[role="meter"]')).toHaveAttribute("aria-valuenow", "24");
    await expect(sidebar).not.toContainText(t("Quota exhausted"));
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    const main = page.getByRole("main");
    await expect(main.locator('[data-quota-window="session"]')).toContainText(/76\s*%/);
    await expect(main.locator('[data-quota-window="weekly"]')).toContainText(/24\s*%/);
    await expect(main.locator('[data-quota-window="weekly"]')).toContainText("2030");
    await expect(main.locator('[data-quota-window="weekly"]')).toContainText(t("Old data"));
    await expect(main.locator('[data-quota-window="credits"]')).toContainText("7.5 credits");
    await expect(main.locator('[data-quota-window="credits"]')).not.toContainText("%");
    await expect(main.locator('[data-quota-window="limit:model:daily"]')).toContainText(t("Provider limit"));
    await expect(main.getByText(t("Not reported"), { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: t("Refresh status and quotas"), exact: true }).click();
    await expect.poll(() => refreshes).toBe(2);
    expect(inference).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`native efforts and a stale catalog remain scoped to the edited connection in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const connection = { id: 1, name: "Native identity", agent: "codex", model: "legacy", enabled: true, status: "CONNECTED", availability: "AVAILABLE", roles: ["analyst", "counter_analyst", "verifier"] };
    await page.route("**/api/ai-connections", route => route.fulfill({ json: [connection] }));
    const native = { id: 4, agent: "codex", identifier: "native-model", name: "Native model", enabled: true, status: "SUPPORTED", capabilities: { reasoning_efforts: ["low", "high"], is_default: true } };
    const items = [native, { ...native, id: 5, identifier: "documented-only", status: "UNKNOWN" }];
    await page.route("**/api/ai-models?*", route => route.fulfill({ json: { items, discovery: { state: "error", reason: "refresh_failed", checked_at: "2020-01-01T00:00:00Z" } } }));
    await page.route("**/api/ai-connections/1/models/refresh?*", route => route.fulfill({ json: { items, discovery: { state: "supported", reason: "catalog_not_entitlement", checked_at: new Date().toISOString() } } }));
    let saved: Record<string, unknown> | null = null;
    await page.route("**/api/ai-connections/1", route => { saved = route.request().postDataJSON(); return route.fulfill({ json: { ...connection, ...saved } }); });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    await page.getByRole("region", { name: "Native identity", exact: true }).getByRole("button", { name: t("Edit"), exact: true }).click();
    const model = page.getByLabel(t("Model"), { exact: true });
    await expect(model).toHaveValue("legacy");
    await expect(model.locator('option[value="documented-only"]')).toHaveCount(0);
    await expect(page.getByText(t("Previous catalog; refresh needed"), { exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Refresh models"), exact: true }).click();
    await expect(page.getByText(t("Previous catalog; refresh needed"), { exact: true })).toHaveCount(0);
    await model.selectOption("native-model");
    const effort = page.getByLabel(t("Reasoning"), { exact: true });
    await expect(effort.locator("option")).toHaveText([t("Default"), "low", "high"]);
    await effort.selectOption("high");
    if (info.project.name === "desktop") {
      const positions = await Promise.all([page.getByLabel(t("Assistant provider"), { exact: true }), model, effort].map(async field => (await field.boundingBox())!.y));
      expect(Math.max(...positions)-Math.min(...positions)).toBeLessThan(3);
    }
    await page.screenshot({ path: `../.local/v291-ui/native-model-${language}-${info.project.name}.png`, fullPage: true, animations: "disabled" });
    await page.getByRole("button", { name: t("Save connection"), exact: true }).click();
    await expect.poll(() => saved).toMatchObject({ model: "native-model", reasoning_effort: "high" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`sources and publication connectors have separate settings and old creation links still work in ${language}`, async ({ page }) => {
    await setup(page, language);
    await page.goto("/admin");
    const navigation = page.getByRole("navigation", { name: t("Administration"), exact: true });
    await expect(navigation.getByRole("button")).toHaveText([t("General"), t("AI & Agents"), t("Sources & environments"), t("Connectors")]);
    await navigation.getByRole("button", { name: t("Sources & environments"), exact: true }).click();
    const sources = page.getByRole("navigation", { name: t("Sources & environments"), exact: true });
    await expect(sources.getByRole("button")).toHaveText([t("Git sources"), t("PostgreSQL connections"), t("Environments")]);
    await sources.getByRole("button", { name: t("PostgreSQL connections"), exact: true }).click();
    await expect(page.getByRole("button", { name: t("Add connection"), exact: true })).toBeVisible();
    await sources.getByRole("button", { name: t("Environments"), exact: true }).click();
    await expect(page.getByRole("heading", { name: t("New environment"), exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: t("Ticket publication connectors"), exact: true })).toHaveCount(0);
    await page.goto("/");
    await expect(page.getByLabel(t("Your question or change"), { exact: true })).toHaveCount(0);
    await page.goto("/?new=1");
    await expect(page).toHaveURL(/\/analyses\?new=1$/);
    await expect(page.getByLabel(t("Your question or change"), { exact: true })).toBeVisible();
  });
}
