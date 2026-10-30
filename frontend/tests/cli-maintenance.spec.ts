import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";

for (const language of ["en", "fr"] as const) {
  test(`CLI version and explicit update stay inside the connection card in ${language}`, async ({ page }) => {
    const t = (key: string) => translate(key, language);
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { authenticated: true, mode: "local" } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { language, name: "SpecHelper", primary_color: "#2563eb" } }));
    await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [] } }));
    await page.route("**/api/ai-connections", route => route.fulfill({ json: [{ id: 1, agent: "codex", name: "ChatGPT", enabled: true, status: "CONNECTED", availability: "AVAILABLE", quota_windows: {} }] }));
    let tool = { agent: "codex", installed_version: "0.163.0", latest_version: "0.165.0", update_available: true, update_status: "", update_error: "" };
    await page.route("**/api/cli-tools", route => route.fulfill({ json: { items: [tool] } }));
    let updates = 0;
    await page.route("**/api/cli-tools/codex/update", route => {
      updates++;
      tool = { ...tool, update_status: "QUEUED" };
      return route.fulfill({ json: tool });
    });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    const card = page.locator("#ai-connection-1");
    const version = card.locator(".connection-cli-version");
    await expect(version).toContainText("v0.163.0");
    await expect(version).toHaveClass(/text-xs.*muted/);
    expect(await version.evaluate(element => Boolean(element.nextElementSibling?.classList.contains("connection-quotas")))).toBe(true);
    expect(updates).toBe(0);
    await version.getByRole("button", { name: t("Update"), exact: true }).click();
    await expect(version).toContainText(t("Update waiting for current tasks"));
    expect(updates).toBe(1);
    tool = { ...tool, update_status: "RUNNING" };
    await expect(version).toContainText(t("Updating…"));
    tool = { ...tool, update_status: "DONE", installed_version: "0.165.0", update_available: false };
    await expect(version).toContainText("v0.165.0");
    await expect(version.getByRole("button", { name: t("Update"), exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
