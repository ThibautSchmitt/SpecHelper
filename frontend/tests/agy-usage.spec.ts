import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(key, language);
  test(`native Antigravity logo and independent quota pools in ${language}`, async ({ page }) => {
    const observed = new Date().toISOString();
    const windows = {
      "gemini-weekly": { remaining_percent: 0, exhausted: true, scope: "model_pool", model_pool: "gemini", group_name: "Gemini Models", window_type: "w[REDACTED]kly", observed_at: observed, resets_at: "2030-01-01T00:00:00Z" },
      "3p-weekly": { remaining_percent: 25, exhausted: false, scope: "model_pool", model_pool: "claude_gpt", group_name: "Claude and GPT models", window_type: "w[REDACTED]kly", observed_at: observed },
    };
    const connections = ["gemini-native", "claude-native"].map((model, index) => ({ id: index+1, name: model, model, agent: "antigravity", enabled: true, status: "CONNECTED", availability: "AVAILABLE", quota_windows: windows, quota_status: { state: "available", checked_at: observed }, quota_identity_id: "shared" }));
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { authenticated: true, mode: "local" } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb" } }));
    await page.route("**/api/connections", route => route.fulfill({ json: { ais: connections, databases: [] } }));
    await page.route("**/api/ai-connections", route => route.fulfill({ json: connections }));
    await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4", max_calls: 20, allow_same_family_fallback: true, global_instructions_requires_review: true, global_instructions: "" } }));
    await page.goto("/admin");
    const gemini = page.locator('[data-connection="1"]');
    const claude = page.locator('[data-connection="2"]');
    await expect(gemini).toContainText(t("Quota exhausted"));
    await expect(claude.locator('[role="meter"]')).toHaveAttribute("aria-valuenow", "25");
    await expect(claude).not.toContainText(t("Quota exhausted"));
    const logo = gemini.locator('img[data-provider="antigravity"]');
    await expect(logo).toHaveAttribute("src", "/antigravity.svg");
    await expect.poll(() => logo.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBe(true);
    const save = page.getByRole("button", { name: t("Save global instructions"), exact: true });
    await expect(save).toBeDisabled();
    await expect(page.getByLabel(t("Global instructions"), { exact: true })).toHaveValue("");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    const main = page.getByRole("main");
    await expect(main.locator('[data-quota-window="gemini-weekly"]')).toContainText(t("Gemini Models"));
    await expect(main.locator('[data-quota-window="3p-weekly"]')).toContainText(t("Claude and GPT models"));
    await expect(main.locator('[data-quota-window="3p-weekly"]')).toContainText(t("Weekly quota"));
    await page.getByRole("button", { name: t("Roles and orchestration"), exact: true }).click();
    await expect(main).toContainText(t("Explores the request and project sources."));
    await expect(main).toContainText(t("Stored shared instructions match a configured credential. Review them in General settings."));
    await expect(main).not.toContainText("optional verifier");
    await expect(main).not.toContainText("Keep configured credentials");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
