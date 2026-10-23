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

test("settings have one bottom access point and exactly three nonduplicated sections", async ({ page }) => {
  await setup(page);
  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Main navigation", exact: true });
  await expect(navigation.getByRole("link")).toHaveText(["Requests", "Questions", "Tickets"]);
  await expect(navigation.getByRole("link", { name: "Settings", exact: true })).toHaveCount(0);
  const settings = page.locator(".sidebar-admin");
  await expect(settings).toHaveAccessibleName("Settings");
  await settings.focus();
  await settings.press("Enter");
  const tabs = page.getByRole("navigation", { name: "Administration", exact: true });
  await expect(tabs.getByRole("button")).toHaveText(["General", "AI & Agents", "Environments"]);
  await expect(page.getByRole("group", { name: "Theme", exact: true })).toHaveCount(1);
  await expect(page.getByLabel("Instance name", { exact: true })).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "Request activity", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "AI connections", exact: true })).toHaveCount(0);
  await tabs.getByRole("button", { name: "AI & Agents", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Analysis configuration", exact: true })).toHaveCount(1);
  await expect(page.getByLabel("Independent counter-analysis", { exact: true })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Save analysis settings", exact: true })).toHaveCount(1);
  await expect(page.getByLabel("Instance name", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Theme", exact: true })).toHaveCount(0);
  await tabs.getByRole("button", { name: "Environments", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sources Git", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analysis configuration", exact: true })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Theme", exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("environment ticket editors fetch and save only their own connectors", async ({ page }) => {
  await setup(page);
  const reads: string[] = [];
  let saved: Record<string, unknown> | null = null;
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, async (route) => {
    if (route.request().method() === "POST") {
      saved = route.request().postDataJSON();
      return route.fulfill({ status: 201, json: { id: 31, ...saved } });
    }
    const environmentId = new URL(route.request().url()).searchParams.get("environment_id");
    // The shared status sidebar may read connector metadata without an environment.
    if (environmentId) reads.push(environmentId);
    return route.fulfill({ json: environmentId === "1" ? [{ id: 11, name: "Production GitHub", platform: "github", status: "CONNECTED", environment_id: 1 }] : [] });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  const production = page.locator('.environment-connectors[aria-label="Ticket connectors for Production"]');
  const staging = page.locator('.environment-connectors[aria-label="Ticket connectors for Staging"]');
  await expect(production.getByRole("button", { name: /Production GitHub/ })).toBeVisible();
  await expect(staging.getByRole("button", { name: /Production GitHub/ })).toHaveCount(0);
  await staging.getByRole("button", { name: "New connector", exact: true }).click();
  await staging.getByLabel("Connector name", { exact: true }).fill("Staging GitHub");
  await staging.getByLabel("Dedicated issue publication token", { exact: true }).fill("synthetic-publication-only-token");
  await staging.getByRole("button", { name: "Save connector", exact: true }).click();
  await expect.poll(() => saved).toMatchObject({ environment_id: 2, name: "Staging GitHub", platform: "github" });
  expect(reads).toContain("1");
  expect(reads).toContain("2");
  expect(new Set(reads)).toEqual(new Set(["1", "2"]));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
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
  for (const name of ["Edit", "Delete", "Disable", "Refresh status and quotas"]) {
    const button = primary.getByRole("button", { name, exact: true });
    await expect(button).toBeVisible();
    await expect(button).toHaveAttribute("title", name);
    await expect(button.locator("svg")).toHaveCount(1);
    await expect(button).toHaveText("");
  }
  await expect(page.getByText("Session quota: 42% remaining", { exact: true })).toBeVisible();
  await expect(page.getByText("Weekly quota: Unknown", { exact: true })).toHaveCount(2);
  await expect(page.getByText("This Claude Code version does not expose account quotas. Check your provider usage page.", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Provider usage", exact: true })).toHaveAttribute("href", "https://claude.ai/settings/usage");
  await primary.getByRole("button", { name: "Refresh status and quotas", exact: true }).click();
  await expect.poll(() => checked).toBe(true);
  await expect(page.getByText("Quota refresh failed. Last known observations are preserved.", { exact: true })).toBeVisible();
  await expect(page.getByText("Session quota: 42% remaining", { exact: true })).toBeVisible();
  await expect(page.getByText("Last checked:", { exact: false })).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("legacy unassigned connectors require an environment without resubmitting credentials", async ({ page }) => {
  await setup(page);
  let payload: Record<string, unknown> | null = null;
  const connector = { id: 70, name: "Legacy tracker", platform: "jira", base_url: "https://tracker.example.test", username: "team", api_version: "v1", projects: ["TEAM"], default_project: "TEAM", has_secret: true, environment_id: null };
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, (route) => route.fulfill({ json: new URL(route.request().url()).searchParams.has("environment_id") ? [] : [connector] }));
  await page.route("**/api/ticket-connectors/70", (route) => {
    payload = route.request().postDataJSON();
    return route.fulfill({ json: { ...connector, ...payload } });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  const heading = page.getByRole("heading", { name: "Unassigned ticket connectors", exact: true });
  await expect(heading).toBeVisible();
  const section = heading.locator("..");
  const assign = section.getByRole("button", { name: "Assign Legacy tracker", exact: true });
  await expect(assign).toBeDisabled();
  await section.getByLabel("Environment", { exact: true }).selectOption("2");
  await assign.click();
  await expect.poll(() => payload).toMatchObject({ environment_id: 2, name: "Legacy tracker", projects: ["TEAM"] });
  expect(payload).not.toHaveProperty("secret");
  expect(payload).not.toHaveProperty("app_token");
  await expect(heading).toHaveCount(0);
});
