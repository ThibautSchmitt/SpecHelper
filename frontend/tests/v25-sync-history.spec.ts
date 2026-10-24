import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const endpoint = "**/api/environments/1/synchronization-history";
const created = "2026-10-24T09:00:00Z";
const started = "2026-10-24T09:00:01Z";
const finished = "2026-10-24T09:00:10Z";
const translate = (language: "en" | "fr", key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
async function setup(page: Page, language: "en" | "fr") {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb" } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { github: { status: "CONNECTED" }, ais: [], databases: [] } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4" } }));
  await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Production", status: "READY", repositories: [], revision: 1 }] }));
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "fr" ? "dark" : "light");
  await page.goto("/admin");
  await page.getByRole("button", { name: translate(language, "Environments"), exact: true }).click();
  return page.locator("details").filter({ has: page.locator("summary").filter({ hasText: new RegExp(`^${translate(language, "Synchronization history")}$`) }) });
}
for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(language, key);
  test(`Git synchronization history loads only on demand and retains successful diagnostics in ${language}`, async ({ page }, info) => {
    let release = () => {};
    const pending = new Promise<void>(resolve => { release = resolve; });
    const methods: string[] = [];
    const history = await setup(page, language);
    await page.route(endpoint, async route => {
      methods.push(route.request().method());
      await pending;
      await route.fulfill({ json: [
        { id: 33, status: "RUNNING", created_at: created, started_at: started, finished_at: null, error: "" },
        { id: 32, status: "ERROR", created_at: created, started_at: started, finished_at: finished, error: "Git synchronization failed: check authentication and read permissions." },
        { id: 31, status: "DONE", created_at: created, started_at: started, finished_at: finished, error: "" },
      ] });
    });
    expect(methods).toEqual([]);
    await history.locator("summary").click();
    await expect(history.getByRole("status")).toHaveText(t("Loading synchronization history…"));
    await expect(page.getByRole("button", { name: t("Environments"), exact: true })).toBeEnabled();
    release();
    const rows = history.getByRole("list", { name: t("Recorded synchronizations"), exact: true }).getByRole("listitem");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toContainText("#33"); await expect(rows.nth(0)).toContainText(t("In progress"));
    await expect(rows.nth(1)).toContainText("#32"); await expect(rows.nth(1)).toContainText(t("Failed")); await expect(rows.nth(1)).toContainText(t("Git synchronization failed: check authentication and read permissions."));
    await expect(rows.nth(2)).toContainText("#31"); await expect(rows.nth(2)).toContainText(t("Completed"));
    expect(await rows.nth(2).locator("time").evaluateAll(elements => elements.map(element => element.getAttribute("datetime")))).toEqual([created, started, finished]);
    await expect(rows.nth(0)).toContainText(t("Unknown"));
    if (language === "fr") expect(t("Git synchronization failed: check authentication and read permissions.")).not.toBe("Git synchronization failed: check authentication and read permissions.");
    expect(methods).toEqual(["GET"]);
    await history.locator("summary").click(); await history.locator("summary").click();
    await expect(rows.nth(2)).toBeVisible(); expect(methods).toEqual(["GET"]);
    await history.getByRole("button", { name: t("Refresh history"), exact: true }).click();
    await expect.poll(() => methods).toEqual(["GET", "GET"]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (language === "fr" && info.project.name === "mobile") await history.screenshot({ path: "../.local/v25-ui/sync-history-fr-mobile.png", animations: "disabled" });
  });
  test(`synchronization diagnostic failure retries read-only and empty history stays explicit in ${language}`, async ({ page }) => {
    let available = false;
    const methods: string[] = [];
    const history = await setup(page, language);
    await page.route(endpoint, route => {
      methods.push(route.request().method());
      return available ? route.fulfill({ json: [] }) : route.fulfill({ status: 503, json: { detail: "Git synchronization failed: check authentication and read permissions." } });
    });
    expect(methods).toEqual([]);
    await history.locator("summary").click();
    await expect(history.getByRole("alert")).toContainText(t("Git synchronization failed: check authentication and read permissions."));
    await expect(history.getByText(t("No synchronization jobs have been recorded for this environment."), { exact: true })).toHaveCount(0);
    available = true; await history.getByRole("button", { name: t("Retry"), exact: true }).click();
    await expect(history.getByText(t("No synchronization jobs have been recorded for this environment."), { exact: true })).toBeVisible();
    await expect(history.getByRole("alert")).toHaveCount(0);
    expect(methods).toEqual(["GET", "GET"]);
  });
}
