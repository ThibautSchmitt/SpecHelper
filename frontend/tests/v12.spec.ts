import { test, expect } from "./fixtures";

test("new request: optional comparison and explicit queue state", async ({
  page,
}) => {
  const id = "44444444-4444-4444-8444-444444444444";
  const detail = {
    id,
    need: "Export active contracts only",
    confrontation: true,
    status: "QUEUED",
    environment_id: 1,
    environment_name: "Validation",
    created_at: new Date().toISOString(),
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
    versions: [],
    messages: [],
    latest_version: null,
    analysis_runs: [],
  };
  await page.route("**/api/settings", (r) =>
    r.fulfill({
      json: {
        name: "SpecHelper",
        primary_color: "#2563eb",
        short_label: "",
        allow_confrontation: true,
        language: "en",
      },
    }),
  );
  await page.route("**/api/environments", (r) =>
    r.fulfill({
      json: [{ id: 1, name: "Validation", status: "READY", repositories: [] }],
    }),
  );
  await page.route("**/api/requests", (r) => {
    if (r.request().method() === "POST") {
      expect(r.request().postDataJSON()).toEqual({
        environment_id: 1,
        need: detail.need,
        confrontation: true,
      });
      return r.fulfill({ status: 201, json: detail });
    }
    return r.fulfill({ json: [] });
  });
  await page.route(`**/api/requests/${id}**`, (r) =>
    r.fulfill({ json: detail }),
  );
  await page.goto("/");
  await page.getByLabel("Environment", { exact: true }).selectOption("1");
  await page.getByLabel("Describe your need").fill(detail.need);
  await page.getByLabel("Compare multiple analyses", { exact: true }).check();
  await page
    .getByRole("button", { name: "Analyze request", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(id));
  await expect(
    page.getByRole("heading", { name: "Your request is queued" }),
  ).toBeVisible();
  await expect(
    page.getByText("A comparison of two independent analyses was requested.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", {
      name: "check connections in Administration",
    }),
  ).toBeVisible();
});

test("compact admin: independent connections and targeted probe", async ({
  page,
}) => {
  const ais = [
    {
      id: 1,
      name: "ChatGPT",
      agent: "codex",
      status: "CONNECTED",
      availability: "QUOTA_EXHAUSTED",
      enabled: true,
      account: "ChatGPT",
    },
    {
      id: 2,
      name: "Claude",
      agent: "claude",
      status: "CONNECTED",
      availability: "AVAILABLE",
      enabled: true,
      account: "Claude",
    },
  ];
  let tested = false;
  await page.route("**/api/ai-connections", (r) => r.fulfill({ json: ais }));
  await page.route("**/api/connections", (r) =>
    r.fulfill({
      json: {
        github: { status: "CONNECTED", account: "Fixture" },
        ais,
        databases: [],
      },
    }),
  );
  await page.route("**/api/ai-connections/2/test", (r) => {
    tested = true;
    return r.fulfill({ json: ais[1] });
  });
  await page.goto("/admin");
  const navigation = page.getByRole("navigation", {
    name: "Administration",
    exact: true,
  });
  await expect(navigation.getByRole("button")).toHaveCount(3);
  await expect(
    navigation.getByRole("button", { name: "Agents and skills" }),
  ).toHaveCount(0);
  await expect(
    page
      .getByRole("region", { name: "ChatGPT", exact: true })
      .getByText("Quota exhausted", { exact: true }),
  ).toBeVisible();
  const claude = page.getByRole("region", { name: "Claude", exact: true });
  await expect(claude.getByText("Available", { exact: true })).toBeVisible();
  await claude
    .getByRole("button", { name: "Test connection", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Connection checked.");
  expect(tested).toBe(true);
});

test("PostgreSQL: one test and three simple statuses", async ({ page }) => {
  await page.route("**/api/connections", (r) =>
    r.fulfill({
      json: {
        github: { status: "CONNECTED", account: "Fixture" },
        ais: [],
        databases: [],
      },
    }),
  );
  await page.route("**/api/connections/databases", (r) => {
    const value = r.request().postDataJSON();
    expect(value.url).toBe(
      "postgresql://reader:fixture-password@db.example/business",
    );
    return r.fulfill({
      status: 201,
      json: {
        id: 21,
        status: "CONNECTED",
        checks: { connection: true, read: true, read_only: true },
      },
    });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  const database = page.getByRole("region", {
    name: "PostgreSQL connections",
    exact: true,
  });
  await database
    .getByRole("button", { name: "Add connection", exact: true })
    .click();
  await database
    .getByLabel("Connection name", { exact: true })
    .fill("Read-only");
  await database.getByLabel("Use a PostgreSQL URL", { exact: true }).check();
  await database
    .getByLabel("PostgreSQL URL", { exact: true })
    .fill("postgresql://reader:fixture-password@db.example/business");
  await expect(
    database.getByRole("button", { name: "Test connection", exact: true }),
  ).toHaveCount(1);
  await database
    .getByRole("button", { name: "Test connection", exact: true })
    .click();
  await expect(database.getByRole("status")).toContainText("Connection OK");
  await expect(database.getByRole("status")).toContainText("Read query OK");
  await expect(database.getByRole("status")).toContainText("Read-only");
  await expect(
    database.getByText(/table count|postgresql version|schema list/i),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("administration: no internal agent or skill settings", async ({
  page,
}) => {
  const calls: string[] = [];
  await page.route("**/api/analysis-options", (r) => {
    calls.push(r.request().method());
    return r.fulfill({ json: { agents: [], skills: [] } });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Instance", exact: true }).click();
  await expect(page.getByLabel("Instance name")).toBeVisible();
  await expect(
    page.getByText("Advanced analysis options", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByLabel("Proposal review", { exact: true })).toHaveCount(
    0,
  );
  await expect(page.getByText("ROLE:", { exact: false })).toHaveCount(0);
  expect(calls).toEqual([]);
});
