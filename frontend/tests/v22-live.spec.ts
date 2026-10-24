import { test, expect } from "./fixtures";
import { execFileSync } from "node:child_process";
import path from "node:path";

function fixture(action: string, target: string) {
  const root = path.resolve(process.cwd(), "..");
  return execFileSync(path.join(root, "backend/.venv/bin/python"), [path.join(root, "frontend/tests/fixture.py"), action, target], { cwd: root, encoding: "utf8" });
}

test("guided business decisions, conflict approval and immutable artifacts use the real isolated API", async ({ page }, info) => {
  const name = `business-${info.project.name}`;
  fixture("seed", name);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  try {
    await page.goto("/");
    await page.getByLabel("Environment", { exact: true }).selectOption({ label: `[E2E] ${name}` });
    await page.getByLabel("Describe your need", { exact: true }).fill("Let operations choose the business scope of a contracts export.");
    await page.getByRole("button", { name: "Analyze request", exact: true }).click();
    await expect(page).toHaveURL(/\/requests\/[a-f0-9-]+$/);
    const id = page.url().split("/").at(-1)!;
    const read = () => page.request.get(`/api/requests/${id}`).then(response => response.json());
    await expect(page.getByRole("heading", { name: "Your request is queued", exact: true })).toBeVisible();
    fixture("business-clarify", id);
    const clarification = page.getByRole("region", { name: "Business clarification", exact: true });
    await expect(clarification.getByRole("radio")).toHaveCount(3);
    await clarification.getByRole("radio", { name: "B — All contracts with a warning", exact: true }).check();
    await clarification.getByRole("button", { name: "Validate and continue", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Your request is queued", exact: true })).toBeVisible();
    const initial = await read();
    expect(initial.decision_revision).toBe(1);
    expect(initial.decisions).toHaveLength(1);
    expect(initial.decisions[0].option_id).toBe("all");
    const originalRule = initial.decisions[0].value;
    fixture("business-result", id);
    await expect(page.getByRole("button", { name: "Copy goal.md", exact: true })).toBeVisible();
    const first = await page.request.get(`/api/requests/${id}/versions/1`).then(response => response.json());
    expect(first.decisions_snapshot[0].option_id).toBe("all");
    expect(first.ticket.expected_behavior).toContain(originalRule);
    expect(first.ticket.acceptance_criteria).toContain(originalRule);
    expect(first.markdown).toContain(originalRule);
    expect(first.goal_markdown).toContain(originalRule);
    const firstTicket = first.markdown, firstGoal = first.goal_markdown;

    const decisions = page.getByRole("region", { name: "Confirmed business decisions", exact: true });
    await decisions.getByRole("button", { name: "Revise decision", exact: true }).click();
    await decisions.getByRole("radio", { name: "A — Active contracts only", exact: true }).check();
    await decisions.getByRole("button", { name: "Review this change", exact: true }).click();
    const review = decisions.getByRole("region", { name: "Review a changed decision", exact: true });
    await expect(review).toContainText(originalRule);
    await expect(review).toContainText("Export active contracts only.");
    const unchanged = await read();
    expect(unchanged.decision_revision).toBe(1);
    expect(unchanged.decision_history).toHaveLength(1);
    expect(unchanged.decisions[0].option_id).toBe("all");
    await review.getByRole("button", { name: "Confirm the change", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Your request is queued", exact: true })).toBeVisible();
    const changed = await read();
    expect(changed.decision_revision).toBe(2);
    expect(changed.decisions[0].option_id).toBe("active");
    expect(changed.decision_history).toHaveLength(2);
    expect(changed.decisions[0].previous_id).toBe(initial.decisions[0].id);
    await expect(page.getByText("The displayed result still uses earlier decisions. A new analysis must reflect your latest choices before validation.", { exact: true })).toBeVisible();
    await expect(decisions.getByRole("button", { name: "Validate business intent", exact: true })).toHaveCount(0);

    // An explicit version URL always shows that version's immutable decisions,
    // even while it is still the latest completed result and a new run is queued.
    await page.goto(`/requests/${id}?version=1`);
    await expect(decisions).toContainText(originalRule);
    await expect(decisions.getByRole("button", { name: "Revise decision", exact: true })).toHaveCount(0);
    fixture("business-result", id);
    await page.goto(`/requests/${id}`);
    await expect(page.getByLabel("Result version", { exact: true })).toContainText("Current version · v2");
    const second = await read();
    expect(second.latest_version.decisions_snapshot[0].option_id).toBe("active");
    expect(second.latest_version.ticket.acceptance_criteria).toContain("Export active contracts only.");
    expect(second.latest_version.goal_markdown).toContain("Export active contracts only.");
    await decisions.getByRole("button", { name: "Validate business intent", exact: true }).click();
    await expect(decisions.getByRole("button", { name: "Reopen for changes", exact: true })).toBeVisible();
    expect((await read()).validated_version).toBe(2);
    await decisions.getByRole("button", { name: "Reopen for changes", exact: true }).click();
    await expect(decisions.getByRole("button", { name: "Revise decision", exact: true })).toBeVisible();
    expect((await read()).validated_version).toBeNull();

    const historical = await page.request.get(`/api/requests/${id}/versions/1`).then(response => response.json());
    expect(historical.markdown).toBe(firstTicket);
    expect(historical.goal_markdown).toBe(firstGoal);
    expect(historical.decisions_snapshot[0].option_id).toBe("all");
    await page.getByLabel("Result version", { exact: true }).selectOption("1");
    await expect(decisions).toContainText(originalRule);
    await expect(decisions.getByRole("button", { name: "Revise decision", exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  } finally {
    fixture("cleanup", name);
  }
});
