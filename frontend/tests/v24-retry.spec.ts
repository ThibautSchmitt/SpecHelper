import { test, expect, openAnalysisReport } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const id = "24242424-2424-4242-8242-242424242424";
const stamp = "2026-10-24T10:00:00Z";
const settings = { reliability_protocol: "2.4", global_instructions: "", global_instruction_version: 4, max_calls: 12, allow_same_family_fallback: true, verifier_enabled: true, allow_confrontation: true };
const reasons = ["A legacy skill requests an unsupported capability or provider and remains inactive.", "Legacy role-specific or permission-sensitive instructions were preserved for review and are not applied to current system roles."];
async function setup(page: Page, language: "en" | "fr") {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb" } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { github: { status: "CONNECTED" }, ais: [], databases: [] } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: settings }));
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "fr" ? "dark" : "light");
}
function detail(workflow: "request" | "question") {
  const version = { id: "version-1", number: 1, format_version: "1.2", language: "en", status: "READY", created_at: stamp, ticket: workflow === "request" ? { title: "Previously checked export", context: "ORIGINAL_PUBLISHED_EVIDENCE", need: "Preserve the checked filter." } : {}, explanation: workflow === "question" ? { title: "Previously checked explanation", summary: "ORIGINAL_PUBLISHED_EVIDENCE" } : {}, markdown: "# Previous result", answer_markdown: "# Previous explanation", goal_markdown: "# Previous goal", artifacts: {} };
  return { id, workflow, analysis_protocol: "2.4", need: "Check export boundaries", status: workflow === "request" ? "ERROR" : "CANCELLED", language: "en", environment_id: 1, environment_name: "Production", created_at: stamp, confrontation: true, baseline: [], database: {}, questions: [], conversation: [], progress: [], understanding: "Check rare states", error: "", attachments: [], ticket: null, markdown: null, versions: [{ number: 1, status: "READY", created_at: stamp }], latest_version: version, messages: [] };
}
for (const language of ["en", "fr"] as const) {
  const t = (key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
  for (const workflow of ["request", "question"] as const) {
    for (const accepted of [true, false]) test(`explicit ${workflow} retry ${accepted ? "queues" : "retains stopping error"} and preserves prior evidence in ${language}`, async ({ page }) => {
      await setup(page, language);
      const base = workflow === "question" ? "questions" : "requests";
      let value = detail(workflow);
      const previous = structuredClone(value.latest_version);
      await page.route(`**/api/${base}/${id}`, route => route.fulfill({ json: value }));
      let attempts = 0;
      await page.route(`**/api/${base}/${id}/retry`, route => {
        attempts += 1; expect(route.request().method()).toBe("POST");
        if (!accepted) return route.fulfill({ status: 409, json: { detail: "The previous execution is still stopping. Retry shortly." } });
        value = { ...value, status: "QUEUED", error: "" }; return route.fulfill({ json: value });
      });
      await page.goto(`/${base}/${id}`);
      await openAnalysisReport(page);
      await expect(page.getByText("ORIGINAL_PUBLISHED_EVIDENCE", { exact: true }).last()).toBeVisible();
      await page.getByRole("button", { name: t("Resume analysis"), exact: true }).click();
      await expect.poll(() => attempts).toBe(1);
      if (accepted) {
        await expect(page.locator(".investigation-progress").getByText(t("In queue"), { exact: true })).toBeVisible();
        await expect(page.getByRole("button", { name: t("Resume analysis"), exact: true })).toHaveCount(0);
      } else {
        await expect(page.getByRole("main").getByRole("alert")).toHaveText(t("The previous execution is still stopping. Retry shortly."));
        await expect(page.getByRole("button", { name: t("Resume analysis"), exact: true })).toBeEnabled();
        await expect(page.locator(".investigation-progress").getByText(t("In queue"), { exact: true })).toHaveCount(0);
      }
      expect(value.latest_version).toEqual(previous);
      await expect(page.getByText("ORIGINAL_PUBLISHED_EVIDENCE", { exact: true }).last()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
    test(`activity opens the failed ${workflow} and resumes from its conversation in ${language}`, async ({ page }, info) => {
      await setup(page, language);
      const base = workflow === "question" ? "questions" : "requests";
      let value = detail(workflow);
      let attempts = 0;
      await page.route(`**/api/${base}/${id}`, route => route.fulfill({ json: value }));
      await page.route(`**/api/${base}/${id}/retry`, route => {
        attempts++;
        if (attempts === 1) return route.fulfill({ status: 409, json: { detail: "The previous execution is still stopping. Retry shortly." } });
        value = { ...value, status: "QUEUED", error: "" };
        return route.fulfill({ json: value });
      });
      await page.route("**/api/queue", route => route.fulfill({ json: [{ id: 1, kind: "analysis", workflow, request_id: id, title: "Retry target", status: "ERROR", queue_state: "ERROR", request_status: "ERROR", created_at: stamp, started_at: stamp, finished_at: stamp, environment_name: "Production", href: `/${base}/${id}`, can_retry: true, error: "Recorded failure" }] }));
      await page.goto("/questions");
      await page.getByRole("button", { name: t("Activity"), exact: true }).click();
      const queue = page.getByRole(info.project.name === "mobile" ? "dialog" : "complementary", { name: t("Activity"), exact: true });
      await expect(queue.locator('[data-job="1"]')).toContainText(t("Analysis interrupted"));
      await queue.getByRole("link", { name: t("See the problem"), exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/${base}/${id}`));
      await page.getByRole("button", { name: t("Resume analysis"), exact: true }).click();
      await expect(page.getByRole("main").getByRole("alert")).toHaveText(t("The previous execution is still stopping. Retry shortly."));
      await page.getByRole("button", { name: t("Resume analysis"), exact: true }).click();
      await expect(page.locator(".investigation-progress").getByText(t("In queue"), { exact: true })).toBeVisible();
      expect(attempts).toBe(2);
    });
  }
  test(`legacy migration warnings remain explicit without automatic instruction promotion in ${language}`, async ({ page }) => {
    await setup(page, language);
    let written: Record<string, unknown> | null = null;
    const config = { ...settings, preserved_guidance_review: true, migration_review: [{ kind: "skill", slug: "unsupported-review", reason: reasons[0] }, { kind: "instructions", reason: reasons[1] }] };
    await page.route("**/api/orchestration-settings", route => { if (route.request().method() === "PUT") { written = route.request().postDataJSON(); config.global_instructions = written!.global_instructions as string; } return route.fulfill({ json: config }); });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("Orchestration"), exact: true }).click();
    await expect(page.getByLabel(t("Allow limited AI diversity"), { exact: true })).toBeVisible();
    expect(config.preserved_guidance_review).toBe(true);
    expect(config.migration_review).toHaveLength(2);
    await expect(page.getByLabel(t("Global instructions"), { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: t("Save"), exact: true })).toBeDisabled();
    expect(written).toBeNull();
  });
}
