import { test, expect } from "./fixtures";
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
      await expect(page.getByText("ORIGINAL_PUBLISHED_EVIDENCE", { exact: true }).last()).toBeVisible();
      await page.getByRole("button", { name: t("Resume analysis"), exact: true }).click();
      await expect.poll(() => attempts).toBe(1);
      if (accepted) {
        await expect(page.getByRole("heading", { name: t(workflow === "question" ? "Your question is queued" : "Your request is queued"), exact: true })).toBeVisible();
        await expect(page.getByRole("button", { name: t("Resume analysis"), exact: true })).toHaveCount(0);
      } else {
        await expect(page.getByRole("main").getByRole("alert")).toHaveText(t("The previous execution is still stopping. Retry shortly."));
        await expect(page.getByRole("button", { name: t("Resume analysis"), exact: true })).toBeEnabled();
        await expect(page.getByRole("heading", { name: t(workflow === "question" ? "Your question is queued" : "Your request is queued"), exact: true })).toHaveCount(0);
      }
      expect(value.latest_version).toEqual(previous);
      await expect(page.getByText("ORIGINAL_PUBLISHED_EVIDENCE", { exact: true }).last()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
    test(`queue retries only terminal ${workflow} jobs and exposes a rejected retry in ${language}`, async ({ page }, info) => {
      await setup(page, language);
      const base = workflow === "question" ? "questions" : "requests";
      const cancelledId = id.slice(0, -1) + "5";
      const job = (number: number, state: string) => ({ id: number, kind: "analysis", workflow, title: `Retry target ${number}`, request_id: number === 2 ? cancelledId : number === 1 ? id : id.slice(0, -1) + String(number + 5), status: state, queue_state: state, request_status: state, created_at: stamp, started_at: stamp, finished_at: stamp, elapsed_seconds: 400, queue_position: null, environment_name: "Production", operation: "Source analysis", agent: null, assignments: [], assignment_state: "unassigned", error: "", href: `/${base}/${id}`, can_retry: true });
      let values = [job(1, "ERROR"), job(2, "CANCELLED"), job(3, "RUNNING"), job(4, "PAUSED")];
      await page.route("**/api/queue", route => route.fulfill({ json: values }));
      await page.route(`**/api/${base}/${id}/retry`, route => { values = values.map(item => item.id === 1 ? { ...item, status: "QUEUED", queue_state: "WAITING_AI", can_retry: false } : item); return route.fulfill({ json: { status: "QUEUED" } }); });
      await page.route(`**/api/${base}/${cancelledId}/retry`, route => route.fulfill({ status: 409, json: { detail: "The previous execution is still stopping. Retry shortly." } }));
      await page.goto("/questions");
      const mobile = info.project.name === "mobile";
      if (mobile) await page.getByRole("button", { name: t("Task queue"), exact: true }).click();
      const queue = page.getByRole(mobile ? "dialog" : "complementary", { name: t("Task queue"), exact: true });
      await expect(queue.getByRole("button", { name: /Retry target/ })).toHaveCount(2);
      await queue.locator('[data-job="1"]').getByRole("button", { name: t("Resume analysis: {title}").replace("{title}", "Retry target 1"), exact: true }).click();
      await expect(queue.locator('[data-job="1"]')).toHaveAttribute("data-state", "WAITING_AI");
      await queue.locator('[data-job="2"]').getByRole("button", { name: t("Resume analysis: {title}").replace("{title}", "Retry target 2"), exact: true }).click();
      await expect(queue.locator('[data-job="2"]').getByRole("alert")).toHaveText(t("The previous execution is still stopping. Retry shortly."));
      await expect(queue.locator('[data-job="2"]')).toHaveAttribute("data-state", "CANCELLED");
      await expect(queue.locator('[data-job="3"]')).toHaveAttribute("data-state", "RUNNING");
    });
  }
  test(`legacy migration warnings remain explicit without automatic instruction promotion in ${language}`, async ({ page }) => {
    await setup(page, language);
    let written: Record<string, unknown> | null = null;
    const config = { ...settings, preserved_guidance_review: true, migration_review: [{ kind: "skill", slug: "unsupported-review", reason: reasons[0] }, { kind: "instructions", reason: reasons[1] }] };
    await page.route("**/api/orchestration-settings", route => { if (route.request().method() === "PUT") { written = route.request().postDataJSON(); config.global_instructions = written!.global_instructions as string; } return route.fulfill({ json: config }); });
    await page.goto("/admin");
    await expect(page.getByText(t("Previous custom guidance was preserved for review. Check custom skills and the deployment migration notes before enabling it."), { exact: true })).toBeVisible();
    await expect(page.getByLabel(t("Global instructions"), { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: t("Save global instructions"), exact: true })).toHaveCount(0);
    expect(written).toBeNull();
  });
}
