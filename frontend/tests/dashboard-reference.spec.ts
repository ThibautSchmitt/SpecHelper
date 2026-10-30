import { test, expect } from "./fixtures";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";
import type { Page } from "@playwright/test";

async function expectThemeParity(page: Page, selectors: string[]) {
  const layouts = [];
  for (const theme of ["light", "dark"] as const) {
    await page.evaluate(value => {
      localStorage.setItem("spechelper-theme", value);
      window.dispatchEvent(new StorageEvent("storage", { key: "spechelper-theme", newValue: value }));
    }, theme);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    for (const button of await page.locator('button:visible, [data-slot="button"]:visible, .action-menu > summary:visible, .queue-card > div > a:visible').all()) {
      if (await button.evaluate(element => Boolean(element.closest(".color-options")))) continue;
      await expect(button).toHaveCSS("border-radius", "7px");
    }
    for (const tag of await page.locator('.badge:visible, .activity-state:visible, .coverage-state:visible, .analysis-state-pill:visible, .analysis-intent-pill:visible, .analysis-environment-pill:visible, .queue-total:visible').all()) {
      await expect(tag).toHaveCSS("border-radius", "9999px");
    }
    const layout = [];
    for (const selector of selectors) {
      layout.push(await page.locator(selector).first().evaluate(element => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return {
          size: [rect.width, rect.height].map(value => Math.round(value * 100) / 100),
          display: style.display, font: style.font, padding: style.padding,
          radius: style.borderRadius, borders: [style.borderTopWidth, style.borderLeftWidth],
        };
      }));
    }
    layouts.push(layout);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (await page.locator(".home-hero").count()) {
      await expect(page.locator(".home-hero")).toHaveCSS("background-image", /dashboard-landscape\.svg/);
    }
  }
  expect(layouts[0]).toEqual(layouts[1]);
}

for (const language of ["fr", "en"] as const) {
  const t = (key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
  test(`reference dashboard keeps real states, shortcuts and private draft transfer in ${language}`, async ({ page }, info) => {
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { authenticated: true, mode: "local" } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#0f766e", short_label: "Team" } }));
    const at = new Date().toISOString();
    const row = { id: "29292929-2929-4292-8292-292929292929", title: "Contract export", need: "Contract export. Include archived records.", status: "NEEDS_CLARIFICATION", result_state: "clarification", workflow: "request", intent_resolved: true, environment_name: "Production", href: "/analyses/29292929-2929-4292-8292-292929292929", latest_activity_at: at };
    await page.route("**/api/analyses/overview", route => route.fulfill({ json: { sections: { clarify: { count: 1, items: [row] }, active: { count: 0, items: [] }, consult: { count: 0, items: [] } } } }));
    await page.route("**/api/analyses?*", route => route.fulfill({ json: { items: [row], total: 1, page: 1, pages: 1 } }));
    await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [] } }));
    await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Production", status: "READY", repositories: [], revision: 1, synced_at: at }] }));
    await page.route("**/api/ai-connections", route => route.fulfill({ json: [{ id: 1, name: "ChatGPT", agent: "codex", enabled: true, status: "CONNECTED", availability: "AVAILABLE", roles: ["analyst", "counter_analyst", "verifier"], quota_windows: { session: { remaining_percent: 51, observed_at: at }, weekly: { remaining_percent: 32, observed_at: at } } }] }));
    await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4", role_coverage: { complete: true, roles: Object.fromEntries(["analyst", "counter_analyst", "verifier"].map(role => [role, { configured: [1], available: [1] }])) } } }));
    await page.route("**/api/library/skill", route => route.fulfill({ json: [{ enabled: true }, { enabled: true }] }));
    await page.route("**/api/queue", route => route.fulfill({ json: [{ id: 1, kind: "analysis", request_id: row.id, title: row.title, status: "DONE", queue_state: "PAUSED", requires_attention: true, href: row.href, created_at: at, clarification_since: new Date(Date.now() - 41*3600000).toISOString() }] }));
    const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.getByRole("heading", { name: "SpecHelper", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: t("Activity"), exact: true }).locator(".queue-total")).toHaveText("1");
    await expect(page.locator('.sidebar-assistant [data-provider="codex"]')).toBeVisible();
    await expect(page.locator(".home-result")).toHaveCount(1);
    await expectThemeParity(page, [".home-hero", ".home-launch button", ".home-bucket", ".sidebar-admin"]);
    const activityToggle = page.getByRole("button", { name: t("Activity"), exact: true });
    const collapsedToggleBounds = await activityToggle.boundingBox();
    await activityToggle.click();
    await expect(page.locator(".queue-card:visible")).toBeVisible();
    await expect(page.locator(".task-queue h2")).toHaveCount(0);
    if (info.project.name === "desktop") {
      const expandedToggleBounds = await activityToggle.boundingBox();
      expect(expandedToggleBounds).toEqual(collapsedToggleBounds);
      const panelBounds = await page.locator("#desktop-task-queue").boundingBox();
      const firstCardBounds = await page.locator("#desktop-task-queue .queue-card").first().boundingBox();
      expect(expandedToggleBounds!.x).toBeGreaterThan(panelBounds!.x);
      expect(expandedToggleBounds!.y + expandedToggleBounds!.height).toBeLessThanOrEqual(firstCardBounds!.y);
    }
    await expectThemeParity(page, [".queue-card:visible", ".queue-card:visible > div > a"]);
    if (info.project.name === "mobile") await page.keyboard.press("Escape");
    else await page.getByRole("button", { name: t("Activity"), exact: true }).click();
    await page.getByRole("navigation", { name: t("Main navigation"), exact: true }).getByRole("link", { name: t("Analyses"), exact: true }).click();
    const analysis = page.locator(".analysis-row").first();
    if (info.project.name === "desktop") {
      await analysis.hover();
      await expect(analysis).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, -2)");
      await page.mouse.move(0, 0);
    }
    await analysis.focus();
    await expect(analysis).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, -2)");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(analysis).toHaveCSS("transform", "none");
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await expectThemeParity(page, [".analysis-row", ".analysis-state-pill"]);
    await page.getByRole("navigation", { name: t("Main navigation"), exact: true }).getByRole("link", { name: t("Home"), exact: true }).click();
    await page.getByLabel(t("A question about your project"), { exact: true }).fill("Keep this business draft out of the URL.");
    await page.getByRole("button", { name: t("New analysis"), exact: true }).click();
    await expect(page).toHaveURL(/\/analyses\?new=1&from_home=1$/);
    await expect(page.getByLabel(t("Your question or change"), { exact: true })).toHaveValue("Keep this business draft out of the URL.");
    await expect(page.locator(".dashboard-settings-nav")).toHaveCount(0);
    await page.getByRole("link", { name: t("Administration"), exact: true }).click();
    const navigation = page.getByRole("navigation", { name: t("Administration"), exact: true });
    await navigation.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(t("AI & Agents"));
    const preview = page.getByRole("region", { name: "ChatGPT", exact: true }).filter({ has: page.getByRole("heading", { name: "ChatGPT", exact: true }) });
    await expect(preview.locator(".connection-role-tag")).toHaveText([t("Analyst"), t("Counter-analyst"), t("Verifier")]);
    const tagColors = await preview.locator(".connection-tag").evaluateAll(tags => tags.map(tag => getComputedStyle(tag).color));
    expect(new Set(tagColors).size).toBe(4);
    await expect(preview.getByRole("definition").filter({ hasText: /51\s*%/ })).toBeHidden();
    await preview.locator(".connection-quotas > summary").click();
    await expect(preview.getByRole("definition").filter({ hasText: /51\s*%/ })).toBeVisible();
    await expect(page.getByRole("complementary", { name: t("Analysis configuration"), exact: true })).toContainText(t("Role coverage"));
    await expect(preview.getByRole("progressbar")).toHaveCount(2);
    await expectThemeParity(page, [".ai-connection-card", ".connection-quota-preview", ".ai-settings-summary"]);
    await page.screenshot({ path: `../.local/reference-tests/ai-${language}-${info.project.name}.png`, fullPage: true, animations: "disabled" });
    await navigation.getByRole("button", { name: t("Environments"), exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(t("Environments"));
    await expect(page.getByText(t("Synchronized"), { exact: true })).toBeVisible();
    await expectThemeParity(page, [".environment-card", '.environment-card .badge[data-state="READY"]']);
    await navigation.getByRole("button", { name: t("Appearance"), exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(t("Settings"));
    await page.getByRole("button", { name: t("Light"), exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    // Tailwind dark variants must follow the app preference, not the OS setting.
    await page.evaluate(() => {
      const probe = document.createElement("span");
      probe.dataset.testid = "theme-variant-probe";
      probe.className = "hidden dark:block";
      probe.textContent = "Theme variant";
      document.body.append(probe);
    });
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.getByTestId("theme-variant-probe")).toBeHidden();
    await page.getByRole("button", { name: t("Dark"), exact: true }).click();
    await page.emulateMedia({ colorScheme: "light" });
    await expect(page.getByTestId("theme-variant-probe")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}
