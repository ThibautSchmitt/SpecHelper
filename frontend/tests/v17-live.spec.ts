import { test, expect } from "./fixtures";
import { execFileSync } from "node:child_process";
import path from "node:path";

function fixture(action: string, target: string) {
  const root = path.resolve(process.cwd(), "..");
  return execFileSync(path.join(root, "backend/.venv/bin/python"), [path.join(root, "frontend/tests/fixture.py"), action, target], { cwd: root, encoding: "utf8" });
}

test("question, clarification, versioned documents and derived ordinary request use the real isolated API", async ({ page }, info) => {
  const name = `question-${info.project.name}`;
  fixture("seed", name);
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  try {
    await page.goto("/questions");
    await page.getByLabel("Environment", { exact: true }).selectOption({ label: `[E2E] ${name}` });
    await page.getByLabel("Your question", { exact: true }).fill("How are active contracts validated before export?");
    await page.getByLabel("Attachments", { exact: false }).setInputFiles({ name: "question.md", mimeType: "text/markdown", buffer: Buffer.from("Explain the active filter.") });
    await page.getByRole("button", { name: "Analyze question", exact: true }).click();
    await expect(page).toHaveURL(/\/questions\/[a-f0-9-]+$/);
    const questionId = page.url().split("/").at(-1)!;
    await expect(page.getByRole("heading", { name: "Your question is queued", exact: true })).toBeVisible();
    fixture("clarify", questionId);
    await page.getByLabel("Should the export include active contracts only?", { exact: true }).fill("Yes, active contracts only.");
    await page.getByRole("button", { name: "Answer and continue", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Your question is queued", exact: true })).toBeVisible();
    fixture("question-result", questionId);
    await expect(page.getByRole("button", { name: "Copy explanation", exact: true })).toBeVisible();
    await expect(page.getByTestId("question-explanation")).toContainText("contracts/export.py");
    await expect(page.getByTestId("question-explanation")).toContainText("c".repeat(40));
    await expect(page.getByRole("link", { name: "question.md", exact: true })).toHaveAttribute("href", `/api/questions/${questionId}/attachments/` + (await page.request.get(`/api/questions/${questionId}`).then(r => r.json())).attachments[0].id);
    await page.getByRole("button", { name: "Copy explanation", exact: true }).click();
    await expect(page.getByRole("button", { name: "Copied!", exact: true })).toBeVisible();
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download explanation", exact: true }).click();
    expect((await downloadPromise).suggestedFilename()).toBe("answer.md");
    for (const kind of ["business", "technical", "mixed"]) {
      await page.getByLabel("Documentation format", { exact: true }).selectOption(kind);
      await page.getByRole("button", { name: "Generate documentation", exact: true }).click();
      const download = page.waitForEvent("download");
      await page.getByRole("link", { name: "Download documentation", exact: true }).first().click();
      expect((await download).suggestedFilename()).toMatch(/\.md$/);
    }
    await page.getByRole("link", { name: "Create a request", exact: true }).click();
    await expect(page.getByLabel("Environment", { exact: true })).toHaveValue(String((await page.request.get(`/api/questions/${questionId}`).then(r => r.json())).environment_id));
    await expect(page.getByLabel("Describe your need", { exact: true })).toHaveValue("");
    await expect(page.getByLabel("Attach question context", { exact: false })).toBeChecked();
    await page.getByText("Review transferred context", { exact: true }).click();
    await expect(page.getByText("Historical imports were not checked.", { exact: false })).toBeVisible();
    await page.getByLabel("Describe your need", { exact: true }).fill("Add a CSV export action for active contracts.");
    await page.getByRole("button", { name: "Analyze request", exact: true }).click();
    await expect(page).toHaveURL(/\/requests\/[a-f0-9-]+$/);
    const requestId = page.url().split("/").at(-1)!;
    expect(requestId).not.toBe(questionId);
    await expect(page.getByText("Internal Markdown context", { exact: true })).toBeVisible();
    const derived = await page.request.get(`/api/requests/${requestId}`).then(r => r.json());
    expect(derived.source_question).toMatchObject({ id: questionId, version: 1 });
    expect(derived.attachments).toHaveLength(1);
    expect(derived.attachments[0]).toMatchObject({ internal: true, source_question: { id: questionId, version: 1 } });
    fixture("derived-result", requestId);
    await expect(page.getByRole("link", { name: "goal.md", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy for Jira", exact: true })).toBeVisible();
    await page.goto(`/questions/${questionId}`);
    await expect(page.getByRole("link", { name: "Add a CSV export action for active contracts.", exact: true })).toHaveAttribute("href", `/requests/${requestId}`);
    await expect(page.getByRole("button", { name: "Copy explanation", exact: true })).toBeVisible();
    expect(await page.getByRole("link", { name: "goal.md", exact: true }).count()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  } finally {
    fixture("cleanup", name);
  }
});
