import { test, expect } from "./fixtures";
import type { AIConnection } from "../src/components/ai-connections";
import { observedQuota } from "../src/lib/quota";
import { modelFamilyDiversity, publicRoles } from "../src/lib/orchestration";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

test("quota summary selects the configured family and its most restrictive window", () => {
  const now = Date.now();
  const base = { id: 1, account: "test", agent: "antigravity", model: "claude-sonnet", status: "CONNECTED", enabled: true, availability: "AVAILABLE", quota_windows: {
    session: { remaining_percent: 76, observed_at: new Date(now).toISOString() },
    weekly: { remaining_percent: 24, observed_at: new Date(now).toISOString() },
    gemini: { scope: "model_pool", model_pool: "gemini", remaining_percent: 0, exhausted: true },
  } } as AIConnection;
  const quota = observedQuota(base, now);
  expect(quota.remaining).toBe(24);
  expect(quota.state).toBe("Quota remaining");
  expect(quota.partiallyAvailable).toBe(true);
  expect(quota.stale).toBe(false);
  expect(observedQuota({ ...base, enabled: false }, now).partiallyAvailable).toBe(false);
  expect(observedQuota({ ...base, status: "AUTH_ERROR" }, now).partiallyAvailable).toBe(false);
  expect(observedQuota({ ...base, model: "gemini-pro" }, now).state).toBe("Quota exhausted");
  expect(observedQuota({ ...base, quota_windows: {} }, now).remaining).toBeNull();
  expect(observedQuota({ ...base, quota_windows: { session: { remaining_percent: 51, observed_at: "2020-01-01T00:00:00Z" } } }, now).stale).toBe(true);
  expect(observedQuota({ ...base, quota_windows: { session: { remaining_percent: 51, observed_at: new Date(now-60000).toISOString(), reset_at: new Date(now-30000).toISOString() } } }, now).stale).toBe(true);
});

test("diversity uses recorded completed roles rather than independent sessions or provider labels", () => {
  const steps = publicRoles.map((public_role, index) => ({ public_role, status: "DONE", model_family: ["gpt", "claude", "gemini"][index] }));
  expect(modelFamilyDiversity(steps)).toBe("Three model families · full diversity");
  expect(modelFamilyDiversity(steps.map((step, index) => ({ ...step, model_family: index ? "claude" : "gpt" })))).toBe("Two model families · partial diversity");
  expect(modelFamilyDiversity(steps.map(step => ({ ...step, model_family: "gpt" })))).toBe("One model family · limited diversity");
  expect(modelFamilyDiversity(steps.slice(0, 2))).toBe("Missing step · incomplete verification");
  expect(modelFamilyDiversity(steps.map(step => ({ ...step, model_family: "" })))).toBe("Model-family diversity not recorded");
});

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
  test(`environment editing reuses connections and connector checks remain explicit in ${language}`, async ({ page }) => {
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language } }));
    await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4" } }));
    await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [{ id: 7, name: "Shared read-only DB", status: "CONNECTED" }] } }));
    await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Production", status: "READY", revision: 1, database_id: 7, repositories: [], synced_at: "2026-10-27T10:00:00Z" }] }));
    let rows = [{ id: 1, environment_id: 1, name: "GitLab tracker", platform: "gitlab", status: "UNKNOWN", checked_at: null as string | null, error: "" }];
    await page.route("**/api/ticket-connectors?*", route => route.fulfill({ json: rows }));
    let tests = 0;
    await page.route("**/api/ticket-connectors/1/test", route => { tests++; rows = rows.map(row => ({ ...row, status: "CONNECTED", checked_at: new Date().toISOString() })); return route.fulfill({ json: rows[0] }); });
    await page.goto("/admin?tab=environments");
    await expect(page.getByText(t("Synchronized"), { exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Edit {name}").replace("{name}", "Production"), exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel(t("Database"), { exact: true })).toHaveValue("7");
    await expect(dialog.getByRole("region", { name: t("Associated publication connectors"), exact: true })).toContainText("GitLab tracker");
    await expect(dialog.getByRole("link", { name: new RegExp(t("Manage Git connections")) })).toHaveAttribute("href", "/admin?tab=environments&sources=git");
    await expect(dialog.getByRole("link", { name: new RegExp(t("Manage PostgreSQL connections")) })).toHaveAttribute("target", "_blank");
    await dialog.getByRole("button", { name: t("Cancel"), exact: true }).click();
    await page.getByRole("link", { name: t("Administration"), exact: true }).click();
    await page.getByRole("navigation", { name: t("Administration"), exact: true }).getByRole("button", { name: t("Connectors"), exact: true }).click();
    const connector = page.getByRole("region", { name: "GitLab tracker", exact: true });
    await expect(connector).toContainText(t("Not tested"));
    expect(tests).toBe(0);
    await connector.getByRole("button", { name: t("Test {name}").replace("{name}", "GitLab tracker"), exact: true }).click();
    await expect(connector).toContainText(t("Connected"));
    expect(tests).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`title editing preserves the full original business text and exposes recorded diversity in ${language}`, async ({ page }, info) => {
    const id = "29292929-2929-4292-8292-292929292929";
    const original = "Explain contract eligibility. Preserve every exception and the original wording.";
    const at = new Date().toISOString();
    const version = { id: "v1", number: 1, run_number: 1, status: "READY", language, created_at: at, explanation: { title: "Answer title", summary: "Eligibility depends on contract conditions." }, evidence: { claims: [], blocking: false, limitations: [], database: { status: "not_configured", limitations: [], checks: [], scope: "" } }, markdown: "Reviewed result", artifacts: {}, decisions_snapshot: [] };
    let title = "Contract eligibility";
    const detail = () => ({ id, workflow: "question", status: "READY", result_state: "completed", title, need: original, original_need: original, understanding: original, environment_id: 1, environment_name: "Staging", created_at: at, baseline: [], database: {}, questions: [], conversation: [], progress: [], error: "", attachments: [], latest_version: version, versions: [{ number: 1, status: "READY", created_at: at }], messages: [], decisions: [], decision_history: [], decision_revision: 0, evidence: version.evidence, analysis_runs: [{ number: 1, status: "READY", steps: publicRoles.map(public_role => ({ public_role, status: "DONE", model_family: "gpt" })) }] });
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language } }));
    await page.route(`**/api/analyses/${id}`, route => route.fulfill({ json: detail() }));
    const bodies: unknown[] = [];
    await page.route(`**/api/analyses/${id}/title`, route => { const body = route.request().postDataJSON(); bodies.push(body); title = body.title; return route.fulfill({ json: { title } }); });
    const calls: string[] = [];
    page.on("request", request => { if (/\/(analyze|run|continue)$/.test(request.url())) calls.push(request.url()); });
    await page.goto(`/analyses/${id}`);
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    await page.getByRole("button", {name:t("Analysis report"), exact:true}).click();
    await expect(page.getByText(t("One model family · limited diversity"), { exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Edit title"), exact: true }).click();
    await page.getByLabel(t("Analysis title"), { exact: true }).fill("Renamed analysis");
    await page.getByRole("button", { name: t("Save title"), exact: true }).click();
    await expect(page.getByRole("heading", { name: "Renamed analysis", exact: true })).toBeVisible();
    expect(bodies).toEqual([{ title: "Renamed analysis" }]);
    expect(calls).toEqual([]);
    await expect(page.getByText(original, { exact: true }).first()).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "Renamed analysis", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.local/post-ux-after/detail-${language}-${info.project.name}.png`, fullPage: true, animations: "disabled" });
  });

  test(`activity badge excludes running and partial results and persists its closed preference in ${language}`, async ({ page }) => {
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language } }));
    const stamp = new Date().toISOString();
    await page.route("**/api/queue", route => route.fulfill({ json: [
      { id: 1, kind: "analysis", request_id: "1", title: "Clarification", status: "DONE", queue_state: "PAUSED", requires_attention: true, created_at: stamp, href: "/analyses/1", assignments: [{ model: "private-model-diagnostic" }] },
      { id: 2, kind: "analysis", request_id: "2", title: "Failure", status: "ERROR", requires_attention: true, created_at: stamp, href: "/analyses/2", error: "Raw provider exception" },
      { id: 3, kind: "analysis", request_id: "3", title: "Running", status: "RUNNING", requires_attention: false, created_at: stamp, href: "/analyses/3" },
      { id: 4, kind: "analysis", request_id: "4", title: "Partial", status: "DONE", result_status: "partial", requires_attention: false, created_at: stamp, href: "/analyses/4" },
    ] }));
    await page.route("**/api/analyses?*", route => route.fulfill({ json: { items: [], total: 0, page: 1, pages: 0 } }));
    await page.route("**/api/tickets?*", route => route.fulfill({ json: { items: [], total: 0, page: 1, pages: 0, environments: [] } }));
    await page.goto("/analyses");
    const button = page.getByRole("button", { name: t("Activity"), exact: true });
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await expect(button.locator(".queue-total")).toHaveText("2");
    await button.click();
    await page.reload();
    await expect(button).toHaveAttribute("aria-expanded", "true");
    if (!await page.getByRole("dialog", { name: t("Activity"), exact: true }).isVisible()) {
      await page.getByRole("navigation", { name: t("Main navigation"), exact: true }).getByRole("link", { name: t("Tickets"), exact: true }).click();
      await expect(button).toHaveAttribute("aria-expanded", "true");
    }
    const card = page.locator('[data-job="1"]:visible');
    await expect(card.getByRole("link", { name: t("Answer"), exact: true })).toBeVisible();
    await expect(card.locator("pre")).toHaveCount(0);
    await expect(card.locator("details")).toHaveCount(0);
    await expect(card).not.toContainText("private-model-diagnostic");
    if (await page.getByRole("dialog", { name: t("Activity"), exact: true }).isVisible()) await page.keyboard.press("Escape");
    else await button.click();
    await page.getByRole("navigation", { name: t("Main navigation"), exact: true }).getByRole("link", { name: t("Tickets"), exact: true }).click();
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await page.reload();
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await expect(button.locator(".queue-total")).toHaveText("2");
  });
}
