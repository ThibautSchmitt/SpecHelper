import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const orchestration = {
  allow_confrontation: true,
  verifier_enabled: true,
  allow_same_family_fallback: true,
  max_calls: 12,
  timeout_seconds: 240,
  role_instructions: {},
  active_internal_agents: [],
  default_skills: [],
  available_agents: [],
  available_skills: [],
};
const environments = [
  { id: 1, name: "Production", status: "READY", repositories: [], revision: 1 },
  { id: 2, name: "Staging", status: "READY", repositories: [], revision: 1 },
];
async function setup(page: Page) {
  await page.route("**/api/connections", (route) => route.fulfill({ json: { github: { status: "CONNECTED" }, ais: [], databases: [] } }));
  await page.route("**/api/environments", (route) => route.fulfill({ json: environments }));
  await page.route("**/api/requests", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/queue", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/system", (route) => route.fulfill({ json: { jobs: [] } }));
  await page.route("**/api/environments/*/context*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/orchestration-settings", (route) => route.fulfill({ json: orchestration }));
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, (route) => route.fulfill({ json: [] }));
}

test("settings have one bottom access point and exactly four nonduplicated sections", async ({ page }) => {
  await setup(page);
  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Main navigation", exact: true });
  await expect(navigation.getByRole("link")).toHaveText(["Home", "Analyses", "Tickets"]);
  await expect(navigation.getByRole("link", { name: "Settings", exact: true })).toHaveCount(0);
  const settings = page.locator(".sidebar-admin");
  await expect(settings).toHaveAccessibleName("Administration");
  await settings.focus();
  await settings.press("Enter");
  const tabs = page.getByRole("navigation", { name: "Administration", exact: true });
  await expect(tabs.getByRole("button")).toHaveText(["AI & Agents", "Environments", "Ticket publication", "Appearance"]);
  await tabs.getByRole("button", { name: "Appearance", exact: true }).click();
  await expect(page.getByRole("group", { name: "Theme", exact: true })).toHaveCount(1);
  await expect(page.getByLabel("Instance name", { exact: true })).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "Request activity", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "AI connections", exact: true })).toHaveCount(0);
  await tabs.getByRole("button", { name: "AI & Agents", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "AI settings", exact: true }).getByRole("button")).toHaveText(["Connections", "Orchestration", "Skills"]);
  await expect(page.getByRole("region", { name: "Orchestration", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Orchestration", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Orchestration", exact: true })).toHaveCount(1);
  await expect(page.getByLabel("Independent counter-analysis", { exact: true })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(1);
  await expect(page.getByLabel("Instance name", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Theme", exact: true })).toHaveCount(0);
  await tabs.getByRole("button", { name: "Environments", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Git sources", exact: true })).toHaveCount(2);
  await expect(page.getByRole("region", { name: "Orchestration", exact: true })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Theme", exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("publication catalogue loads globally without per-environment credential copies", async ({ page }) => {
  await setup(page);
  const reads: string[] = [];
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, route => {
    reads.push(route.request().url());
    return route.fulfill({ json: [{ id: 11, name: "Shared GitHub", platform: "github", enabled: true, status: "CONNECTED", environment_ids: [1,2], has_secret: true, projects: [] }] });
  });
  await page.goto("/admin?tab=connectors");
  await expect(page.getByRole("heading", { name: "Shared GitHub", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Shared GitHub", exact: true })).toHaveCount(1);
  expect(reads.length).toBeGreaterThan(0);
  expect(reads.every(url => !new URL(url).searchParams.has("environment_id"))).toBe(true);
});

test("compact AI actions expose accessible names and preserve honest quota observations", async ({ page }) => {
  await setup(page);
  const observed = "2026-10-22T10:00:00Z";
  let checked = false;
  const assistants = [
    { id: 41, name: "Primary assistant", agent: "codex", identity_id: "primary", enabled: true, status: "CONNECTED", availability: "AVAILABLE", account: "team", quota_windows: { session: { remaining_percent: 42, observed_at: observed, source: "account/rateLimits/read" } }, quota_status: { state: "available", source: "account/rateLimits/read", checked_at: observed } },
    { id: 42, name: "Backup assistant", agent: "claude", identity_id: "backup", enabled: true, status: "CONNECTED", availability: "AVAILABLE", quota_windows: {}, quota_status: { state: "unavailable", source: "claude auth status", checked_at: observed, reason: "unsupported" } },
  ];
  await page.route("**/api/ai-connections", (route) => route.fulfill({ json: assistants }));
  await page.route("**/api/ai-connections/41/test", (route) => {
    checked = true;
    assistants[0].quota_status = { ...assistants[0].quota_status, state: "error" };
    return route.fulfill({ json: assistants[0] });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "AI & Agents", exact: true }).click();
  const primary = page.getByRole("region", { name: "Primary assistant", exact: true });
  await primary.getByLabel("More actions for Primary assistant", { exact: true }).click();
  for (const name of ["Edit", "Delete", "Disable", "Refresh status and quotas"]) {
    const button = primary.getByRole("button", { name, exact: true });
    await expect(button).toBeVisible();
    await expect(button).toHaveAttribute("title", name);
    await expect(button.locator("svg")).toHaveCount(1);
    await expect(button).toHaveText(name);
  }
  await page.keyboard.press("Escape");
  for (const summary of await page.locator(".connection-quotas > summary").all()) await summary.click();
  await expect(page.getByRole("region", { name: "AI connections", exact: true }).locator('[data-quota-window="session"]').getByText("42% remaining", { exact: true })).toBeVisible();
  await expect(page.getByRole("main").getByText("Not reported", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("This Claude Code version does not expose account quotas. Check your provider usage page.", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Provider usage", exact: true })).toHaveAttribute("href", "https://claude.ai/settings/usage");
  await primary.getByLabel("More actions for Primary assistant", { exact: true }).click();
  await primary.getByRole("button", { name: "Refresh status and quotas", exact: true }).click();
  await expect.poll(() => checked).toBe(true);
  await expect(page.getByText("Quota refresh failed. Last known observations are preserved.", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "AI connections", exact: true }).locator('[data-quota-window="session"]').getByText("42% remaining", { exact: true })).toBeVisible();
  await expect(page.getByText("Last checked:", { exact: false })).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("existing publication connections can be edited without resubmitting secrets", async ({ page }) => {
  await setup(page);
  let payload: Record<string, unknown> | null = null;
  const connector = { id: 70, name: "Legacy tracker", platform: "jira", base_url: "https://tracker.example.test", username: "team", enabled: true, status: "CONNECTED", api_version: "v1", projects: ["TEAM"], default_project: "TEAM", has_secret: true, environment_ids: [] };
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, route => route.fulfill({ json: [connector] }));
  await page.route("**/api/ticket-connectors/70", route => { payload = route.request().postDataJSON(); return route.fulfill({ json: { ...connector, ...payload } }); });
  await page.goto("/admin?tab=connectors");
  await page.getByRole("button", { name: "Edit Legacy tracker", exact: true }).click();
  await expect(page.getByLabel("Secret / API token", { exact: true })).toHaveValue("");
  await page.getByLabel("Connection name", { exact: true }).fill("Retained tracker");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect.poll(() => payload).toMatchObject({ name: "Retained tracker", projects: ["TEAM"] });
  expect(payload).not.toHaveProperty("secret");
  expect(payload).not.toHaveProperty("app_token");
  expect(payload).not.toHaveProperty("environment_id");
});
