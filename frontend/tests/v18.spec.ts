import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const id = "18181818-1818-4818-8818-181818181818";
const timestamp = "2026-10-22T12:00:00Z";
const items = [
  {
    id,
    title: "Clarify the approval rule",
    need: "Clarify the approval rule",
    category: "feature",
    environment_name: "Production",
    status: "READY",
    created_at: timestamp,
    updated_at: timestamp,
  },
  {
    id: "second",
    title: "Fix the import preview",
    need: "Fix the import preview",
    category: "bug",
    environment_name: "Staging",
    status: "QUEUED",
    created_at: timestamp,
    updated_at: timestamp,
  },
];
async function setup(page: Page, language = "en") {
  let settings = {
    name: "SpecHelper",
    primary_color: "#2563eb",
    short_label: "",
    language,
    allow_confrontation: true,
  };
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() === "PUT")
      settings = { ...settings, ...route.request().postDataJSON() };
    await route.fulfill({ json: settings });
  });
  await page.route("**/api/environments", (route) =>
    route.fulfill({
      json: [{ id: 1, name: "Production", status: "READY", repositories: [] }],
    }),
  );
  await page.route("**/api/queue", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/requests", (route) =>
    route.fulfill({ json: items }),
  );
  await page.route("**/api/questions", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/connections", (route) =>
    route.fulfill({
      json: {
        github: { status: "CONNECTED", account: "fixture" },
        ais: [],
        databases: [],
      },
    }),
  );
  await page.route("**/api/system", (route) =>
    route.fulfill({
      json: {
        usage: "",
        runtime: "READY",
        max_analysis_seconds: 295,
        jobs: [],
      },
    }),
  );
  await page.route("**/api/orchestration-settings", (route) =>
    route.fulfill({
      json: {
        verifier_enabled: true,
        allow_same_family_fallback: true,
        max_calls: 10,
        timeout_seconds: 285,
        role_instructions: {},
        active_internal_agents: ["requirement", "code", "writer"],
        default_skills: [],
        available_agents: [],
        available_skills: [],
      },
    }),
  );
  await page.route("**/api/tickets?*", (route) =>
    route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } }),
  );
}

test("light, dark and system share layout, persist across pages and track device changes", async ({
  page,
}) => {
  await setup(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/admin");
  const theme = page.getByRole("group", { name: "Theme", exact: true });
  await expect(
    theme.getByRole("button", { name: "System", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const shape = await page
    .locator(".dashboard")
    .evaluate((node) => getComputedStyle(node).gridTemplateColumns);
  await theme.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(
    await page
      .locator(".dashboard")
      .evaluate((node) => getComputedStyle(node).gridTemplateColumns),
  ).toBe(shape);
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Questions", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "New question", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Settings", exact: true })
    .click();
  await theme.getByRole("button", { name: "Light", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await theme.getByRole("button", { name: "System", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(errors).toEqual([]);
});

for (const workflow of ["request", "question"])
  test(`${workflow} form submits the selected type without any user comparison setting`, async ({
    page,
  }) => {
    await setup(page);
    const base = workflow === "question" ? "/questions" : "/requests";
    const created: unknown[] = [];
    const uploads: string[] = [];
    const item = {
      ...items[0],
      workflow,
      status: "QUEUED",
      environment_id: 1,
      language: "en",
      confrontation: true,
      baseline: [],
      database: {},
      questions: [],
      conversation: [],
      understanding: "",
      progress: [],
      error: "",
      attachments: [],
      ticket: null,
      markdown: null,
      latest_version: null,
      versions: [],
      messages: [],
      analysis_runs: [],
    };
    await page.route(`**/api${base}`, (route) => {
      if (route.request().method() === "POST") {
        created.push(route.request().postDataJSON());
        return route.fulfill({ status: 201, json: item });
      }
      return route.fulfill({ json: [] });
    });
    await page.route(`**/api${base}/${id}/attachments`, (route) => {
      uploads.push(route.request().postDataBuffer()!.toString());
      return route.fulfill({ status: 201, json: { id: "file" } });
    });
    await page.route(`**/api${base}/${id}/analyze`, (route) =>
      route.fulfill({ json: item }),
    );
    await page.route(`**/api${base}/${id}`, (route) =>
      route.fulfill({ json: item }),
    );
    await page.goto(workflow === "question" ? "/questions" : "/");
    await expect(
      page.getByRole("checkbox", {
        name: "Compare multiple analyses",
        exact: true,
      }),
    ).toHaveCount(0);
    await page.getByLabel("Environment", { exact: true }).selectOption("1");
    await page
      .getByRole("group", {
        name: workflow === "question" ? "Question type" : "Request type",
        exact: true,
      })
      .getByRole("button", {
        name: workflow === "question" ? "Architecture" : "Bug",
        exact: true,
      })
      .click();
    await page
      .getByLabel(
        workflow === "question" ? "Your question" : "Describe your need",
        { exact: true },
      )
      .fill("Explain the import approval rules.");
    await page.getByLabel("Attachments", { exact: false }).setInputFiles([
      {
        name: "keep.md",
        mimeType: "text/markdown",
        buffer: Buffer.from("Relevant context"),
      },
      {
        name: "remove.md",
        mimeType: "text/markdown",
        buffer: Buffer.from("Remove this"),
      },
    ]);
    await page
      .getByRole("button", { name: "Remove file remove.md", exact: true })
      .click();
    await page
      .getByRole("button", {
        name: workflow === "question" ? "Analyze question" : "Analyze request",
        exact: true,
      })
      .click();
    await expect(page).toHaveURL(new RegExp(`${base}/${id}$`));
    expect(created).toEqual([
      {
        environment_id: 1,
        need: "Explain the import approval rules.",
        category: workflow === "question" ? "architecture" : "bug",
      },
    ]);
    expect(uploads).toHaveLength(1);
    expect(uploads[0]).toContain("keep.md");
    expect(uploads[0]).not.toContain("remove.md");
  });

test("request list search, status filters and form clearing have real effects", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/");
  await page.getByLabel("Search requests", { exact: true }).fill("approval");
  await expect(
    page.getByRole("link", { name: "Clarify the approval rule", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Fix the import preview", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Filters", exact: true }).click();
  await page
    .getByLabel("Filter by status", { exact: true })
    .selectOption("QUEUED");
  await expect(
    page.getByText("No requests match these filters.", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search requests", { exact: true }).fill("");
  await expect(
    page.getByRole("link", { name: "Fix the import preview", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Describe your need", { exact: true })
    .fill("A draft that can be cleared");
  await page.getByRole("button", { name: "Clear form", exact: true }).click();
  await expect(
    page.getByLabel("Describe your need", { exact: true }),
  ).toHaveValue("");
});

test("settings alone controls independent counter-analysis and color preferences", async ({
  page,
}) => {
  await setup(page);
  const writes: Record<string, unknown>[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/settings") && request.method() === "PUT")
      writes.push(request.postDataJSON());
  });
  await page.goto("/admin");
  await page
    .getByRole("button", { name: "Choose primary color #0f766e", exact: true })
    .click();
  await page.getByRole("button", { name: "Save color", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Color saved.");
  await page
    .getByRole("navigation", { name: "Administration", exact: true })
    .getByRole("button", { name: "AI & Agents", exact: true })
    .click();
  await page
    .getByLabel("Independent counter-analysis", { exact: true })
    .uncheck();
  await page
    .getByRole("button", { name: "Save analysis policy", exact: true })
    .click();
  await expect.poll(() => writes.at(-1)?.allow_confrontation).toBe(false);
  expect(writes.at(-1)?.primary_color).toBe("#0f766e");
});

test("theme and form type controls are translated into French", async ({
  page,
}) => {
  await setup(page, "fr");
  await page.goto("/admin");
  const group = page.getByRole("group", { name: "Thème", exact: true });
  await expect(group.getByRole("button")).toHaveText([
    "Clair",
    "Sombre",
    "Système",
  ]);
  await group.getByRole("button", { name: "Sombre", exact: true }).click();
  await page
    .getByRole("navigation", { name: "Navigation principale" })
    .getByRole("link", { name: "Demandes", exact: true })
    .click();
  await expect(
    page.getByRole("group", { name: "Type de demande", exact: true }),
  ).toContainText("AutomatiqueFonctionnalitéBugDocumentation");
  await expect(
    page.getByText("Confronter plusieurs analyses", { exact: true }),
  ).toHaveCount(0);
});
