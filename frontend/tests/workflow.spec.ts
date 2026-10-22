import { test, expect } from "./fixtures";
import { execFileSync } from "node:child_process";
import path from "node:path";

function fixture(action: string, target: string) {
  const root = path.resolve(process.cwd(), "..");
  return execFileSync(
    path.join(root, "backend/.venv/bin/python"),
    [path.join(root, "frontend/tests/fixture.py"), action, target],
    { cwd: root, encoding: "utf8" },
  );
}

test("administration, theme and business navigation", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Requests", exact: true }),
  ).toBeVisible();
  await page.locator(".sidebar-admin").focus();
  await page.locator(".sidebar-admin").press("Enter");
  await expect(
    page.getByRole("heading", { name: "Instance settings", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "General", exact: true }).click();
  await page.getByLabel("Instance name").fill("SpecHelper — Validation");
  await page.getByLabel("Primary color", { exact: true }).fill("#7c3aed");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByRole("status")).toContainText("saved");
  await expect(
    page.getByRole("link", { name: "SpecHelper — Validation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "New environment" }),
  ).toBeVisible();
  await expect(page.getByLabel("Database", { exact: true })).toHaveValue("");
  await page
    .getByRole("button", { name: "Add a project", exact: true })
    .click();
  await expect(page.getByLabel("Project 2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Remove project 2" }).click();
  await page.getByRole("button", { name: "General", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Instance settings", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Request activity", exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "Requests", exact: true }).click();
  await expect(page.getByLabel("Describe your need")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("request with attachment, clarification, result and export", async ({
  page,
}, testInfo) => {
  const name = testInfo.project.name;
  fixture("seed", name);
  try {
    await page.goto("/");
    await page
      .getByLabel("Environment", { exact: true })
      .selectOption({ label: `[E2E] ${name}` });
    await page
      .getByLabel("Describe your need")
      .fill("I would like to export contracts as CSV.");
    await page.getByLabel("Attachments").setInputFiles({
      name: "need.txt",
      mimeType: "text/plain",
      buffer: Buffer.alloc(11 * 1024 * 1024, "x"),
    });
    await page.getByRole("button", { name: "Analyze request" }).click();
    await expect(page).toHaveURL(/\/requests\/[a-f0-9-]+$/);
    const id = page.url().split("/").at(-1)!;
    await expect(page.getByText("Your request is queued")).toBeVisible();
    fixture("clarify", id);
    await expect(
      page.getByRole("heading", {
        name: "A few details before continuing",
      }),
    ).toBeVisible();
    await page
      .getByLabel("Should the export include active contracts only?")
      .fill("Yes, active contracts only.");
    await page.getByRole("button", { name: "Answer and continue" }).click();
    await expect(
      page.getByRole("heading", {
        name: "A few details before continuing",
      }),
    ).not.toBeVisible();
    fixture("result", id);
    await expect(
      page.getByRole("heading", {
        name: "Export active contracts as CSV",
      }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "need.txt" })).toBeVisible();
    await page.getByRole("button", { name: "Copy for Jira" }).click();
    await expect(page.getByRole("button", { name: "Copied!" })).toBeVisible();
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: "Markdown", exact: true }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("ticket.md");
    await page
      .getByRole("button", { name: "Copy goal.md", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Goal copied!", exact: true }),
    ).toBeVisible();
    const goalPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: "goal.md", exact: true }).click();
    expect((await goalPromise).suggestedFilename()).toBe("goal.md");
    await page
      .getByRole("button", { name: "Continue the discussion", exact: true })
      .click();
    await page
      .getByLabel("Your message", { exact: true })
      .fill("Preserve existing labels.");
    await page
      .getByRole("button", { name: "Send and update proposal" })
      .click();
    await expect(page.getByText("Your request is queued")).toBeVisible();
    fixture("result", id);
    await expect(
      page.getByRole("button", {
        name: "Continue the discussion",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByLabel("Result version")).toContainText(
      "Current version · v2",
    );
    await page.getByLabel("Result version").selectOption("1");
    await expect(
      page.getByRole("link", { name: "goal.md", exact: true }),
    ).toHaveAttribute(
      "href",
      `/api/requests/${id}/versions/1/artifacts/goal.md`,
    );
    await page.getByText("Analysis reference", { exact: true }).click();
    await expect(page.getByText("c".repeat(40), { exact: true })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `../.local/screenshots/result-${name}.png`,
      fullPage: true,
    });
  } finally {
    fixture("cleanup", name);
  }
});
