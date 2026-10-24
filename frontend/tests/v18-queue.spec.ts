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
  if (mobile)
    await page.getByRole("button", { name: "Task queue", exact: true }).click();
  return page.getByRole(mobile ? "dialog" : "complementary", {
    name: "Task queue",
    exact: true,
  });
}

for (const reduced of [false, true])
  test(`queue groups real transitions and ${reduced ? "respects reduced motion" : "slides measured card positions"}`, async ({
    page,
  }) => {
    await setup(page);
    await page.emulateMedia({
      reducedMotion: reduced ? "reduce" : "no-preference",
    });
    const assignment = {
      connection_id: 2,
      connection_name: "Team Claude",
      agent: "claude",
      model: "selected-model",
      public_role: "verifier",
    };
    let values = [
      job(1, "QUEUED"),
      job(2, "RUNNING", {
        assignments: [assignment],
        assignment_state: "current",
        stage: "Focused project analysis",
      }),
      job(3, "PAUSED", {
        pause_reason: "A business answer is needed.",
        stage: "Your answer is needed",
      }),
      job(4, "DONE", {
        assignments: [assignment],
        assignment_state: "previous",
        stage: "Analysis completed",
      }),
      job(5, "ERROR", { error: "The Git server is unavailable." }),
    ];
    await page.route("**/api/queue", (r) => r.fulfill({ json: values }));
    await page.goto("/questions");
    const queue = await openQueue(page, test.info().project.name === "mobile");
    await expect(queue.getByRole("button", { name: "Completed (1)", exact: true })).toHaveAttribute("aria-expanded", "false");
    await queue.getByRole("button", { name: "Completed (1)", exact: true }).click();
    await expect(queue.locator("[data-job]")).toHaveCount(5);
    await expect(queue.locator("[data-job]").first()).toHaveAttribute(
      "data-job",
      "2",
    );
    await expect(
      queue.getByRole("heading", { name: /^In progress(?:\s*\(\d+\))?$/ }),
    ).toBeVisible();
    await expect(
      queue.getByRole("heading", { name: /^Needs clarification(?:\s*\(\d+\))?$/ }),
    ).toBeVisible();
    await expect(queue.locator('[data-job="1"]')).toContainText(
      "AI not assigned",
    );
    await expect(queue.locator('[data-job="1"]')).not.toContainText(
      "Team Claude",
    );
    await expect(queue.locator('[data-job="2"] .queue-assignment')).toContainText("Team Claude");
    await expect(queue.locator('[data-job="2"] .queue-assignment')).toHaveAttribute("title", /selected-model/);
    await expect(queue.locator('[data-job="2"] .queue-role')).toHaveText("Verifier");
    await expect(queue.locator('[data-job="2"]')).toContainText(
      "Focused project analysis",
    );
    await expect(queue.locator('[data-job="3"]')).toHaveAttribute(
      "data-state",
      "PAUSED",
    );
    await expect(queue.locator('[data-job="3"]')).toContainText(
      "A business answer is needed.",
    );
    await expect(queue.locator('[data-job="4"]')).toContainText("Previous AI:");
    await expect(queue.locator('[data-job="5"]')).toContainText(
      "The Git server is unavailable.",
    );
    await expect(queue.locator('[data-job="2"]')).toContainText("#2");
    values = [
      job(2, "DONE", {
        assignments: [assignment],
        assignment_state: "previous",
      }),
      job(1, "RUNNING", {
        assignments: [assignment],
        assignment_state: "current",
        stage: "Checking the explanation and preparing the result",
      }),
      ...values.slice(2),
    ];
    await expect(queue.locator("[data-job]").first()).toHaveAttribute(
      "data-job",
      "1",
      { timeout: 7000 },
    );
    await expect(queue.locator('[data-job="1"]')).toContainText(
      "Checking the explanation and preparing the result",
    );
    const animations = await page.evaluate(
      () =>
        (
          window as Window & {
            queueAnimations?: {
              id: string;
              frames: { transform: string }[];
              timing: { duration: number };
            }[];
          }
        ).queueAnimations || [],
    );
    if (reduced) expect(animations).toEqual([]);
    else {
      expect(
        animations.some(
          (animation) =>
            animation.id === "1" &&
            animation.frames[0].transform !== "translateY(0px)" &&
            animation.timing.duration <= 300,
        ),
      ).toBe(true);
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });

test("synchronization and publication show their real executor without an AI assignment", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/api/queue", (r) =>
    r.fulfill({
      json: [
        job(7, "RUNNING", {
          kind: "sync",
          executor_name: "Git synchronization",
          stage: "Synchronizing repositories",
        }),
        job(8, "RUNNING", {
          kind: "publication",
          executor_name: "Company tracker",
          stage: "Publishing ticket",
        }),
      ],
    }),
  );
  await page.goto("/questions");
  const queue = await openQueue(page, test.info().project.name === "mobile");
  await expect(queue.locator('[data-job="7"]')).toContainText(
    "Git synchronization · No AI execution",
  );
  await expect(queue.locator('[data-job="8"]')).toContainText(
    "Company tracker · No AI execution",
  );
  await expect(queue.getByText("AI not assigned", { exact: true })).toHaveCount(
    0,
  );
});

test("queue loading and transient errors preserve the last observed tasks", async ({
  page,
}) => {
  await setup(page);
  let release: (() => void) | undefined;
  let fail = false;
  const initial = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/queue", async (route) => {
    await initial;
    if (fail)
      return route.fulfill({
        status: 503,
        json: { detail: "Queue temporarily unavailable." },
      });
    return route.fulfill({ json: [job(21, "QUEUED")] });
  });
  await page.goto("/questions");
  const queue = await openQueue(page, test.info().project.name === "mobile");
  await expect(queue.getByRole("status")).toHaveText("Loading tasks…");
  await expect(queue.getByText("No tasks yet.", { exact: true })).toHaveCount(
    0,
  );
  release?.();
  await expect(queue.locator('[data-job="21"]')).toBeVisible();
  fail = true;
  await expect(queue.getByRole("alert")).toContainText(
    "Queue temporarily unavailable.",
    { timeout: 7000 },
  );
  await expect(queue.locator('[data-job="21"]')).toContainText(
    "AI not assigned",
  );
  await expect(queue.getByText("No tasks yet.", { exact: true })).toHaveCount(
    0,
  );
});


for (const theme of ["light", "dark"])
  test(`reference cards bound long text and identify the current assistant in ${theme}`, async ({ page }) => {
    await setup(page);
    await page.addInitScript((value) => localStorage.setItem("spechelper-theme", value), theme);
    const title = "Review the approval workflow for archived contracts and their associated export notifications across all configured business environments";
    const description = "Inspect the existing approval checks, identify the impacted notification handlers and verify the acceptance conditions before proposing a focused change. Preserve the complete explanation for the task detail, including all required conditions and uncertainties.";
    await page.route("**/api/queue", (route) => route.fulfill({ json: [
      job(42, "RUNNING", { title, stage: description, assignment_state: "current", assignments: [{ connection_id: 1, connection_name: "ChatGPT", agent: "codex", model: "recorded-model", public_role: "analyst" }] }),
      job(43, "DONE", { assignment_state: "previous", assignments: [{ connection_id: 2, connection_name: "Claude", agent: "claude", model: "previous-model", public_role: "counter_analyst" }], stage: "Analysis completed" }),
    ] }));
    await page.goto("/questions");
    const queue = await openQueue(page, test.info().project.name === "mobile");
    const card = queue.locator('[data-job="42"]');
    await expect(card.getByText("#42", { exact: true })).toBeVisible();
    await expect(card.locator(".queue-card-title strong")).toHaveAttribute("title", title);
    await expect(card.locator(".queue-description")).toHaveAttribute("title", description);
    await expect(card.locator('[data-provider="codex"]')).toBeVisible();
    await expect(card.locator(".queue-assignment")).toHaveText("ChatGPT");
    await expect(card.locator(".queue-role")).toHaveText("Analyst");
    await expect(card.locator(".queue-assignment")).toHaveAttribute("title", /recorded-model/);
    await expect(card.locator(".queue-assignment")).toHaveAttribute("title", /^Current AI/);
    await queue.getByRole("button", { name: "Completed (1)", exact: true }).click();
    await expect(queue.locator('[data-job="43"] [data-provider="claude"]')).toBeVisible();
    await expect(queue.locator('[data-job="43"] [data-assignment="previous"]')).toHaveAttribute("title", /Previous AI/);
    const bounds = await card.evaluate((node) => {
      const title = node.querySelector("strong")!;
      const description = node.querySelector(".queue-description")!;
      return { titleHeight: title.clientHeight, titleLine: parseFloat(getComputedStyle(title).lineHeight), titleClipped: title.scrollWidth > title.clientWidth, descriptionHeight: description.clientHeight, descriptionLine: parseFloat(getComputedStyle(description).lineHeight), descriptionClipped: description.scrollHeight > description.clientHeight };
    });
    expect(bounds.titleHeight).toBeLessThanOrEqual(bounds.titleLine + 1);
    expect(bounds.titleClipped).toBe(true);
    expect(bounds.descriptionHeight).toBeLessThanOrEqual(bounds.descriptionLine * 2 + 1);
    expect(bounds.descriptionClipped).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await queue.screenshot({ path: test.info().outputPath("task-queue.png"), animations: "disabled" });
  });
