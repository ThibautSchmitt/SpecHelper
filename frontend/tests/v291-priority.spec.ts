import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import { translate, type Language } from "../src/lib/i18n";
import type { AIConnection } from "../src/components/ai-connections";

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
    const card = page.locator("#ai-connection-1");
    await card.locator(".connection-quotas > summary").click();
    await expect(page.locator("#ai-connection-2 .connection-quotas")).not.toHaveAttribute("open", "");
    const window = card.locator('[data-quota-window="session"]');
    await expect(window).toContainText(t("0% remaining"));
    await expect(window.getByRole("progressbar")).toHaveJSProperty("value", 0);
    await expect(page.locator('[data-connection="1"]')).toContainText(t("Quota exhausted"));
    await page.clock.runFor(31000);
    await expect.poll(() => refreshes).toBe(1);
    await expect(window).toContainText(/90\s*%/);
  });

  test(`all quota windows preserve dates, credits and unknown states in ${language}`, async ({ page }) => {
    await setup(page, language);
    const now = new Date().toISOString();
    const reset = "2030-01-07T09:00:00Z";
    const connections: AIConnection[] = [{ id: 1, agent: "codex", name: "Known account", account: "ChatGPT", model: "gpt-6-luna", reasoning_effort: "low", enabled: true, status: "CONNECTED", availability: "AVAILABLE", quota_identity_id: "one", quota_status: { state: "available", checked_at: now }, quota_windows: {
      session: { remaining_percent: 76, observed_at: now, window_minutes: 300, source: "codex_app_server" },
      weekly: { remaining_percent: 24, observed_at: "2020-01-01T00:00:00Z", resets_at: reset, window_minutes: 10080 },
      credits: { remaining_units: 7.5, observed_at: now, unit: "credits" },
      "limit:model:daily": { remaining_percent: 0, scope: "provider_limit", limit_id: "model", observed_at: now },
    } }, { id: 2, agent: "antigravity", name: "Unknown account", account: "", enabled: true, status: "CONNECTED", availability: "AVAILABLE", quota_identity_id: "two", quota_status: { state: "unavailable" }, quota_windows: {} }, {
      id: 3, agent: "antigravity", name: "Antigravity", account: "Antigravity", model: "gemini-3.8-flash-low", enabled: true, status: "CONNECTED", availability: "QUOTA_EXHAUSTED", quota_identity_id: "three", quota_windows: {
        "3p-weekly": { remaining_percent: 70, model_pool: "claude_gpt", scope: "model_pool", group_name: "Claude and GPT models", observed_at: now, source: "antigravity_cli" },
        "gemini-weekly": { remaining_percent: 0, model_pool: "gemini", scope: "model_pool", group_name: "Gemini Models", observed_at: now, source: "antigravity_cli" },
      },
    }];
    await page.route("**/api/ai-connections", route => route.fulfill({ json: connections }));
    let refreshes = 0;
    await page.route("**/api/ai-connections/*/quota/refresh", route => { refreshes++; return route.fulfill({ json: {} }); });
    const inference: string[] = [];
    page.on("request", request => { if (/\/(run|analyze)$/.test(request.url())) inference.push(request.url()); });
    await page.goto("/admin");
    const sidebar = page.locator('[data-connection="1"]');
    await expect(sidebar.getByRole("link")).toContainText(/24\s*%/);
    await expect(sidebar.locator('[role="meter"]')).toHaveCount(0);
    await expect(sidebar).not.toContainText(t("Quota exhausted"));
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    const main = page.getByRole("main");
    await expect(main.locator('.ai-connections > details')).toHaveCount(0);
    await expect(main.locator('[data-quota-window="session"]')).toBeHidden();
    const quotas = main.locator("#ai-connection-1 .connection-quotas > summary");
    await quotas.focus();
    await page.keyboard.press("Enter");
    await expect(main.locator("#ai-connection-2 .connection-quotas")).not.toHaveAttribute("open", "");
    await main.locator("#ai-connection-2 .connection-quotas > summary").click();
    await expect(main.locator('[data-quota-window="session"]')).toContainText(/76\s*%/);
    await expect(main.locator('[data-quota-window="weekly"]')).toContainText(/24\s*%/);
    await expect(main.locator('[data-quota-window="weekly"]')).toContainText("2030");
    await expect(main.locator('[data-quota-window="weekly"]')).toContainText(t("Old data"));
    await expect(main.locator('[data-quota-window="credits"]')).toContainText("7.5 credits");
    await expect(main.locator('[data-quota-window="credits"]')).not.toContainText("%");
    await expect(main.locator('[data-quota-window="limit:model:daily"]')).not.toContainText(t("Provider limit"));
    await expect(main.locator('[data-quota-window="session"] dt')).toHaveText(t("Quota {hours}h").replace("{hours}", "5"));
    await expect(main.locator('[data-quota-window="weekly"] dt')).toHaveText(t("Weekly quota"));
    await expect(main.locator("#ai-connection-1 .connection-model-tag")).toHaveText("gpt-6-luna low");
    await expect(main.locator("#ai-connection-1 .connection-metadata")).toHaveCount(0);
    const antigravity = main.locator("#ai-connection-3");
    await expect(antigravity.locator(".connection-model-tag")).toHaveText("gemini-3.8-flash-low");
    await expect(antigravity.locator(".connection-metadata")).toHaveCount(0);
    await antigravity.locator(".connection-quotas > summary").click();
    await expect(antigravity.locator("[data-quota-window]").first()).toHaveAttribute("data-quota-window", "gemini-weekly");
    await expect(antigravity.locator("[data-quota-window]").nth(1)).toHaveAttribute("data-quota-window", "3p-weekly");
    const gemini = antigravity.locator('[data-quota-window="gemini-weekly"]');
    await expect(gemini.getByRole("progressbar")).toHaveJSProperty("value", 0);
    await expect(gemini).toContainText(t("0% remaining"));
    await expect(gemini).not.toContainText(t("Quota exhausted"));
    await expect(antigravity.locator('[data-quota-window="3p-weekly"]').getByRole("progressbar")).toHaveJSProperty("value", 70);
    await expect(antigravity.locator(".connection-quota-exhausted")).toHaveCount(0);
    await expect(main.locator("#ai-connection-1 .connection-quota-exhausted")).toHaveCount(0);
    await expect(main.locator("#ai-connection-2 .connection-quota-exhausted")).toHaveCount(0);
    connections[2].model = "claude-opus";
    connections[2].availability = "AVAILABLE";
    await page.evaluate(() => window.dispatchEvent(new Event("quota-updated")));
    await expect(antigravity.locator(".connection-quota-exhausted")).toHaveCount(0);
    connections[2].quota_windows!["3p-weekly"]!.remaining_percent = 0;
    await page.evaluate(() => window.dispatchEvent(new Event("quota-updated")));
    await expect(antigravity.getByText(t("Quota depleted"), { exact: true })).toBeVisible();
    connections[2].availability = "QUOTA_EXHAUSTED";
    const { ["3p-weekly"]: thirdParty, ...geminiOnly } = connections[2].quota_windows!;
    connections[2].quota_windows = geminiOnly;
    await page.evaluate(() => window.dispatchEvent(new Event("quota-updated")));
    await expect(antigravity.locator(".connection-quota-exhausted")).toHaveCount(0);
    connections[2].quota_windows = { ...geminiOnly, "3p-weekly": thirdParty };
    connections[0].quota_windows!.session!.remaining_percent = 0;
    await page.evaluate(() => window.dispatchEvent(new Event("quota-updated")));
    await expect(main.locator("#ai-connection-1 .connection-quota-exhausted")).toHaveCount(0);
    connections[0].quota_windows!.weekly!.remaining_percent = 0;
    await page.evaluate(() => window.dispatchEvent(new Event("quota-updated")));
    await expect(main.locator("#ai-connection-1").getByText(t("Quota depleted"), { exact: true })).toBeVisible();
    await expect(main.locator("#ai-connection-2 .connection-quotas").getByRole("progressbar")).toHaveCount(0);
    await expect(main.locator(".connection-quotas").filter({ hasText: /codex_app_server|antigravity_cli|10080|Provider limit|Limite du fournisseur/ })).toHaveCount(0);
    await expect(main.getByText(t("Not reported"), { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: t("Refresh status and quotas"), exact: true }).click();
    await expect.poll(() => refreshes).toBe(3);
    expect(inference).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`native efforts and a stale catalog remain scoped to the edited connection in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const connection = { id: 1, name: "Native identity", agent: "codex", model: "legacy", enabled: true, status: "CONNECTED", availability: "AVAILABLE", roles: ["analyst", "counter_analyst", "verifier"] };
    await page.route("**/api/ai-connections", route => route.fulfill({ json: [connection, { ...connection, id: 2, name: "Other identity", model: "other-model", roles: ["verifier"] }] }));
    const native = { id: 4, agent: "codex", identifier: "native-model", name: "Native model", enabled: true, status: "SUPPORTED", capabilities: { reasoning_efforts: ["low", "medium", "high"], is_default: true } };
    const items = [native, { ...native, id: 5, identifier: "documented-only", status: "UNKNOWN" }, { ...native, id: 6, identifier: "confirmed-model", name: "confirmed-model", status: "AVAILABLE", capabilities: { reasoning_efforts: ["low", "high"], default_effort: "high", is_default: false } }];
    await page.route("**/api/ai-models?*", route => route.fulfill({ json: { items, discovery: { state: "error", reason: "refresh_failed", checked_at: "2020-01-01T00:00:00Z" } } }));
    await page.route("**/api/ai-connections/1/models/refresh?*", route => route.fulfill({ json: { items, discovery: { state: "supported", reason: "catalog_not_entitlement", checked_at: new Date().toISOString() } } }));
    let saved: Record<string, unknown> | null = null;
    await page.route("**/api/ai-connections/1", route => { saved = route.request().postDataJSON(); return route.fulfill({ json: { ...connection, ...saved } }); });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    await page.getByRole("region", { name: "Native identity", exact: true }).getByRole("button", { name: t("Edit"), exact: true }).click();
    const first = page.locator("#ai-connection-1");
    const second = page.locator("#ai-connection-2");
    await expect(first.getByRole("form", { name: t("Edit AI connection"), exact: true })).toBeVisible();
    await expect(second.locator("form")).toHaveCount(0);
    await first.getByLabel(t("Connection name"), { exact: true }).fill("Unsaved title");
    await first.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(first.locator("form")).toHaveCount(0);
    expect(saved).toBeNull();
    await first.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(first.getByLabel(t("Connection name"), { exact: true })).toHaveValue("Native identity");
    await first.getByLabel(t("Connection name"), { exact: true }).fill("Unsaved title");
    await second.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(first.locator("form")).toHaveCount(0);
    await expect(second.getByLabel(t("Connection name"), { exact: true })).toHaveValue("Other identity");
    await second.getByRole("button", { name: t("Cancel"), exact: true }).click();
    await expect(second.locator("form")).toHaveCount(0);
    expect(saved).toBeNull();
    await first.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(first.getByLabel(t("Connection name"), { exact: true })).toHaveValue("Native identity");
    const model = page.getByLabel(t("Model"), { exact: true });
    await expect(model).toHaveValue("legacy");
    await expect(model.locator('option[value="documented-only"]')).toHaveCount(0);
    await expect(page.getByText(t("Previous catalog; refresh needed"), { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: t("Refresh models"), exact: true }).click();
    await expect(page.getByText(t("Previous catalog; refresh needed"), { exact: true })).toHaveCount(0);
    await expect(page.getByText(t("Model catalog available"), { exact: true })).toHaveCount(0);
    await expect(page.getByText(t("Listed model; subscription access not verified"), { exact: true })).toHaveCount(0);
    await expect(model.locator('option[value="native-model"]')).toHaveText("Native model");
    await expect(model.locator('option[value="confirmed-model"]')).toHaveText("confirmed-model");
    await expect(page.getByRole("button", { name: t("Refresh models"), exact: true }).locator("..")).toHaveText(t("Refresh models"));
    const effort = page.getByLabel(t("Reasoning"), { exact: true });
    await model.selectOption("confirmed-model");
    await expect(effort).toHaveValue("high");
    await expect(effort.locator("option")).toHaveText(["low", "high"]);
    await model.selectOption("native-model");
    await expect(effort).toHaveValue("medium");
    await expect(effort.locator("option")).toHaveText(["low", "medium", "high"]);
    await effort.selectOption("high");
    if (info.project.name === "desktop") {
      await expect(page.locator("#ai-config-provider")).toHaveCount(0);
      const positions = await Promise.all([model, effort].map(async field => (await field.boundingBox())!.y));
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
    await expect(navigation.getByRole("button")).toHaveText([t("AI & Agents"), t("Environments"), t("Connectors"), t("Appearance")]);
    await navigation.getByRole("button", { name: t("Environments"), exact: true }).click();
    const sources = page.getByRole("navigation", { name: t("Environment settings"), exact: true });
    await expect(sources.getByRole("button")).toHaveText([t("Configured environments"), t("Manage Git connections"), t("Manage PostgreSQL connections")]);
    await sources.getByRole("button", { name: t("Manage PostgreSQL connections"), exact: true }).click();
    await expect(page.getByRole("button", { name: t("Add connection"), exact: true })).toBeVisible();
    await sources.getByRole("button", { name: t("Configured environments"), exact: true }).click();
    await page.getByRole("button", { name: t("New environment"), exact: true }).click();
    await expect(page.getByRole("heading", { name: t("New environment"), exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: t("Ticket publication connectors"), exact: true })).toHaveCount(0);
    await page.goto("/");
    await expect(page.getByLabel(t("Your question or change"), { exact: true })).toHaveCount(0);
    await page.goto("/?new=1");
    await expect(page).toHaveURL(/\/analyses\?new=1$/);
    await expect(page.getByLabel(t("Your question or change"), { exact: true })).toBeVisible();
  });
}
