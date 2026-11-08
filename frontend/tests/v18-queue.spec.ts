import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const timestamp = "2026-10-22T12:00:00Z";
function job(id: number, state: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    kind: "analysis",
    workflow: "question",
    status: state === "PAUSED" ? "DONE" : state,
    queue_state: state,
    request_status: state === "PAUSED" ? "NEEDS_CLARIFICATION" : "ANALYZING",
    title: `Validation task ${id}`,
    environment_name: "Production",
    operation: "Question analysis",
    created_at: timestamp,
    started_at: state === "RUNNING" ? timestamp : null,
    finished_at: ["DONE", "ERROR", "PAUSED"].includes(state) ? timestamp : null,
    queue_position: state === "QUEUED" ? 1 : null,
    error: "",
    href: "/questions",
    agent: null,
    assignments: [],
    assignment_state: "unassigned",
    stage: "Waiting for a worker",
    ...extra,
  };
}
async function setup(page: Page) {
  await page.route("**/api/environments", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/requests", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/questions", (r) => r.fulfill({ json: [] }));
  await page.addInitScript(() => {
    const native = Element.prototype.animate;
    (window as Window & { queueAnimations?: unknown[] }).queueAnimations = [];
    Element.prototype.animate = function (
      ...args: Parameters<Element["animate"]>
    ) {
      if ((this as HTMLElement).dataset.job) {
        (
          window as Window & { queueAnimations?: unknown[] }
        ).queueAnimations?.push({
          id: (this as HTMLElement).dataset.job,
          frames: args[0],
          timing: args[1],
        });
      }
      return native.apply(this, args);
    };
  });
}
async function openQueue(page: Page, mobile: boolean) {
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  return page.getByRole(mobile ? "dialog" : "complementary", { name: "Activity", exact: true });
}

for (const reduced of [false, true]) test(`activity preserves real transitions and ${reduced ? "reduced motion" : "measured movement"}`, async ({ page }, info) => {
  await setup(page);
  await page.emulateMedia({ reducedMotion: reduced ? "reduce" : "no-preference" });
  let values = [job(1, "QUEUED"), job(2, "RUNNING", { public_role: "verifier", stage_number: 3, stage_count: 3 }), job(3, "PAUSED"), job(4, "DONE"), job(5, "ERROR")];
  await page.route("**/api/queue", route => route.fulfill({ json: values }));
  await page.goto("/questions");
  const queue = await openQueue(page, info.project.name === "mobile");
  const completed = queue.getByRole("button", { name: "Show recent completed activity", exact: true });
  await expect(completed).toHaveAttribute("aria-expanded", "false");
  await expect(queue.locator("[data-job]")).toHaveCount(4);
  await completed.click();
  await expect(queue.locator("[data-job]")).toHaveCount(5);
  await expect(queue.locator("[data-job]").first()).toHaveAttribute("data-job", "3");
  await expect(queue.locator('[data-job="1"]')).toContainText("In queue");
  await expect(queue.locator('[data-job="2"] [data-role="verifier"]')).toHaveText("Validator");
  await expect(queue.locator('[data-job="2"]')).toContainText("Step 3 of 3");
  await expect(queue.locator('[data-job="3"]').getByRole("link", { name: "Answer", exact: true })).toHaveAttribute("href", "/questions");
  await expect(queue.locator('[data-job="5"]')).toContainText("Analysis interrupted");
  await expect(queue.locator('[data-job="5"]').getByRole("link", { name: "See the problem", exact: true })).toBeVisible();
  values = [job(1, "RUNNING", { public_role: "analyst" }), job(2, "DONE"), ...values.slice(2)];
  await expect(queue.locator('[data-job="1"]')).toHaveAttribute("data-state", "RUNNING", { timeout: 7000 });
  await expect(queue.locator('[data-job="1"] [data-role="analyst"]')).toHaveText("Analyst");
  await expect(queue.locator('[data-job="2"]')).toHaveAttribute("data-state", "DONE");
  const animations = await page.evaluate(() => (window as Window & { queueAnimations?: { id: string; timing: { duration: number } }[] }).queueAnimations || []);
  if (reduced) expect(animations).toEqual([]);
  else expect(animations.some(item => item.id === "1" && item.timing.duration <= 300)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("environment updates have no navigation and publications retain their own labels", async ({ page }, info) => {
  await setup(page);
  await page.route("**/api/queue", route => route.fulfill({ json: [job(7, "RUNNING", { kind: "sync" }), job(8, "RUNNING", { kind: "publication" }), job(9, "DONE", { kind: "sync" })] }));
  await page.goto("/questions");
  const queue = await openQueue(page, info.project.name === "mobile");
  await expect(queue.locator('[data-job="7"]')).toContainText("Updating");
  await expect(queue.locator('[data-job="7"]').getByRole("link")).toHaveCount(0);
  await expect(queue.locator('[data-job="8"]')).toContainText("Publishing ticket");
  await expect(queue.locator('[data-job="9"]')).toHaveCount(0);
});

test("activity loading and transient errors preserve the last observed tasks", async ({ page }, info) => {
  await setup(page);
  let release!: () => void, fail = false;
  const initial = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/queue", async route => { await initial; return fail ? route.fulfill({ status: 503, json: { detail: "Temporary outage" } }) : route.fulfill({ json: [job(21, "QUEUED")] }); });
  await page.goto("/questions");
  const queue = await openQueue(page, info.project.name === "mobile");
  await expect(queue.getByRole("status")).toHaveText("Loading activity…");
  release();
  await expect(queue.locator('[data-job="21"]')).toBeVisible();
  fail = true;
  await expect(queue.getByRole("alert")).toHaveText("Activity updates are unavailable. Previous information is retained.", { timeout: 7000 });
  await expect(queue.locator('[data-job="21"]')).toContainText("In queue");
  await expect(queue.getByText("No activity yet.", { exact: true })).toHaveCount(0);
});

for (const theme of ["light", "dark"]) test(`activity cards bound long titles and show the current role in ${theme}`, async ({ page }, info) => {
  await setup(page);
  await page.addInitScript(value => localStorage.setItem("spechelper-theme", value), theme);
  const title = "Review the approval workflow for archived contracts and their associated export notifications across all configured business environments";
  await page.route("**/api/queue", route => route.fulfill({ json: [job(42, "RUNNING", { title, public_role: "analyst" })] }));
  await page.goto("/questions");
  const queue = await openQueue(page, info.project.name === "mobile");
  const card = queue.locator('[data-job="42"]');
  await expect(card.getByRole("heading")).toHaveAttribute("title", title);
  await expect(card.locator('[data-role="analyst"]')).toHaveText("Analyst");
  await expect(card.getByRole("link", { name: "Open analysis", exact: true })).toHaveAttribute("href", "/questions");
  const bounds = await card.getByRole("heading").evaluate(node => ({ height: node.clientHeight, line: parseFloat(getComputedStyle(node).lineHeight) }));
  expect(bounds.height).toBeLessThanOrEqual(bounds.line * 2 + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await queue.screenshot({ path: info.outputPath("activity.png"), animations: "disabled" });
});
