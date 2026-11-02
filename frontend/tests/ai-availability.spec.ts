import { test, expect } from "./fixtures";
import type { AIConnection } from "../src/components/ai-connections";
import { connectionAvailability } from "../src/lib/quota";
import { translate } from "../src/lib/i18n";

const base: AIConnection = { id: 1, name: "Available AI", agent: "codex", model: "gpt-test", account: "fixture", status: "CONNECTED", availability: "AVAILABLE", enabled: true };
const session = { remaining_percent: 0, exhausted: true, window_minutes: 300 };
const weekly = { remaining_percent: 0, exhausted: true, window_type: "weekly" };

test("availability distinguishes observed periods, errors, unknown data and model pools", () => {
  const status = (changes: Partial<AIConnection>) => connectionAvailability({ ...base, ...changes }).key;
  expect(status({})).toBe("available");
  expect(status({ availability: "UNKNOWN", quota_windows: {} })).toBe("unknown");
  expect(status({ status: "UNKNOWN", availability: "UNKNOWN" })).toBe("unknown");
  expect(status({ quota_status: { state: "unavailable" } })).toBe("available"); // Missing quota metadata is not a connection failure.
  expect(status({ quota_windows: { session } })).toBe("waiting");
  expect(status({ quota_windows: { weekly } })).toBe("quota_exhausted");
  expect(status({ quota_windows: { session, weekly } })).toBe("quota_exhausted");
  expect(status({ status: "AUTH_ERROR", quota_windows: { weekly } })).toBe("unavailable");
  expect(status({ availability: "MODEL_UNAVAILABLE", quota_windows: { weekly } })).toBe("unavailable");
  expect(status({ availability: "QUOTA_EXHAUSTED", availability_issue: "UNAVAILABLE", quota_windows: { weekly } })).toBe("unavailable");
  expect(status({ enabled: false, quota_windows: { weekly } })).toBe("unavailable");
  expect(status({ availability: "BUSY" })).toBe("unavailable");
  expect(status({ quota_windows: { daily: { exhausted: true } } })).toBe("unavailable");
  expect(status({ quota_windows: { credits: { remaining_units: 0, exhausted: true } } })).toBe("unavailable");
  expect(status({ quota_windows: { credits: { remaining_units: 0 } } })).toBe("available"); // Credit measurements alone do not establish a block.
  expect(status({ availability: "QUOTA_EXHAUSTED" })).toBe("unknown");
  expect(status({ quota_windows: { session: { exhausted: true } } })).toBe("unknown"); // No inferred five-hour duration.
  const expired = { ...weekly, reset_at: "2020-01-02T00:00:00Z", observed_at: "2020-01-01T00:00:00Z" };
  expect(status({ availability: "QUOTA_EXHAUSTED", quota_windows: { weekly: expired } })).toBe("unknown");
  const pools = { "gemini-weekly": { ...weekly, scope: "model_pool", model_pool: "gemini" }, "3p-weekly": { remaining_percent: 50, scope: "model_pool", model_pool: "claude_gpt", window_type: "weekly" } };
  expect(status({ agent: "antigravity", model: "gemini-pro", quota_windows: pools })).toBe("quota_exhausted");
  expect(status({ agent: "antigravity", model: "claude-sonnet", quota_windows: pools })).toBe("available");
});

for (const language of ["en", "fr"] as const) for (const theme of ["light", "dark"] as const) {
  const t = (key: string) => translate(key, language);
  test(`consistent compact orchestration and safe saving in ${language} ${theme}`, async ({ page }, info) => {
    const connections: AIConnection[] = [
      base,
      { ...base, id: 2, name: "Five-hour AI", availability: "QUOTA_EXHAUSTED", quota_windows: { session } },
      { ...base, id: 3, name: "Weekly AI", availability: "QUOTA_EXHAUSTED", quota_windows: { session, weekly } },
      { ...base, id: 4, name: "Authentication error", status: "AUTH_ERROR", quota_windows: { weekly } },
      { ...base, id: 5, name: "Unknown AI", availability: "UNKNOWN", quota_windows: {} },
      { ...base, id: 6, name: "Unknown quota period", availability: "QUOTA_EXHAUSTED", quota_windows: {} },
      { ...base, id: 7, name: "Connection error with quota", availability: "QUOTA_EXHAUSTED", availability_issue: "UNAVAILABLE", quota_windows: { weekly } },
    ];
    const expected = ["available", "waiting", "quota_exhausted", "unavailable", "unknown", "unknown", "unavailable"];
    let settings = { reliability_protocol: "2.4", allow_same_family_fallback: true, role_coverage: { complete: true, roles: {
      analyst: { configured: [1, 2, 3, 4, 5, 6, 7], available: [1] },
      counter_analyst: { configured: [2, 3], available: [] },
      verifier: { configured: [5], available: [] },
    } } };
    const writes: unknown[] = [];
    let fail = true;
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname.slice(4);
      let json: unknown = [];
      if (path === "/access/session") json = { authenticated: true, mode: "local" };
      if (path === "/settings") json = { name: "SpecHelper", language };
      if (path === "/connections") json = { ais: connections, databases: [] };
      if (path === "/ai-connections") json = connections;
      if (path === "/orchestration-settings") {
        if (route.request().method() === "PUT") {
          writes.push(route.request().postDataJSON());
          if (fail) return route.fulfill({ status: 503, json: { detail: "Save failed" } });
          settings = { ...settings, ...route.request().postDataJSON() };
        }
        json = settings;
      }
      return route.fulfill({ json });
    });
    await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), theme);
    await page.goto("/admin?tab=ai-agents&section=connections");
    const accountBadges = [];
    for (const connection of connections) {
      const badge = page.locator(`#ai-connection-${connection.id} .ai-availability`);
      await expect(badge).toHaveAttribute("data-availability", expected[connection.id-1]);
      await expect(badge).toHaveText(t(connectionAvailability(connection).label));
      accountBadges.push(await badge.textContent());
    }
    const first = page.locator("#ai-connection-1");
    await first.locator(".connection-quotas > summary").click();
    await expect(first.locator(".connection-quotas progress")).toHaveCount(0);
    const weeklyCard = page.locator("#ai-connection-3");
    await weeklyCard.locator(".connection-quotas > summary").click();
    await expect(weeklyCard.locator('[data-quota-window="session"]')).toBeVisible();
    await expect(weeklyCard.locator('[data-quota-window="weekly"]')).toBeVisible();
    await page.getByRole("navigation", { name: t("AI settings"), exact: true }).getByRole("button", { name: t("Orchestration"), exact: true }).click();
    const panel = page.getByRole("region", { name: t("Orchestration"), exact: true });
    await expect(panel.locator(".orchestration-role-card header .badge")).toHaveText([t("Covered"), t("Covered"), t("Covered")]);
    await expect(panel.locator("h4")).toHaveText([t("Analyst"), t("Counter-analyst"), t("Validator")]);
    const analyst = panel.locator('[data-role="analyst"]');
    for (const connection of connections) {
      const badge = analyst.locator(`[data-connection-id="${connection.id}"] .ai-availability`);
      await expect(badge).toHaveText(accountBadges[connection.id-1]!);
      await expect(badge).toHaveAttribute("data-availability", expected[connection.id-1]);
    }
    await expect(panel.locator('[data-role="counter_analyst"]')).toContainText(t("No connection available now"));
    await expect(panel.locator('[data-role="verifier"]')).toContainText(t("Availability not confirmed"));
    await expect(panel.locator("progress")).toHaveCount(0);
    const colors = await analyst.locator(".ai-availability").evaluateAll(elements => elements.map(element => getComputedStyle(element).color));
    expect(new Set(colors.slice(0, 4)).size).toBe(4);
    await expect(panel.getByText(t("Independent review is required"), { exact: true })).toHaveCount(0);
    const save = panel.getByRole("button", { name: t("Save"), exact: true });
    const setting = panel.getByLabel(t("Allow limited AI diversity"), { exact: true });
    await expect(save).toBeDisabled();
    await setting.uncheck();
    await expect(save).toBeEnabled();
    await setting.check();
    await expect(save).toBeDisabled();
    await setting.uncheck();
    await page.evaluate(() => window.dispatchEvent(new Event("quota-updated")));
    await expect(setting).not.toBeChecked();
    await save.click();
    await expect(panel.getByRole("alert")).toContainText("Save failed");
    await expect(setting).not.toBeChecked();
    await expect(save).toBeEnabled();
    fail = false;
    await save.click();
    await expect(panel.getByRole("status")).toHaveText(t("Orchestration settings saved."));
    await expect(save).toBeDisabled();
    expect(writes).toEqual([{ allow_same_family_fallback: false }, { allow_same_family_fallback: false }]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await panel.screenshot({ path: `../.local/orchestration-ui/${language}-${theme}-${info.project.name}.png` });
  });
}
