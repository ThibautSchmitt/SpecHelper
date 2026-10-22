import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const initial = {
  allow_confrontation: true,
  verifier_enabled: true,
  allow_same_family_fallback: true,
  max_calls: 12,
  timeout_seconds: 240,
  role_instructions: {
    analyst: "Check evidence",
    counter_analyst: "Review independently",
    verifier: "Resolve uncertainties",
  },
  active_internal_agents: ["requirement", "code", "writer"],
  default_skills: ["evidence"],
  available_agents: [
    { slug: "code", name: "Code inspection", required: true },
    { slug: "reviewer", name: "Evidence review", required: false },
  ],
  available_skills: [
    { slug: "evidence", name: "Evidence references" },
    { slug: "database", name: "Read-only database inspection" },
  ],
};
const connection = {
  id: 41,
  name: "Team assistant",
  agent: "codex",
  model: "gpt-review",
  enabled: true,
  status: "CONNECTED",
  availability: "AVAILABLE",
  account: "team",
  roles: ["analyst", "verifier"],
  additional_instructions: "Preserve compatibility",
  skill_overrides: { database: false },
};
async function base(page: Page) {
  await page.route("**/api/connections", (r) =>
    r.fulfill({
      json: { github: { status: "CONNECTED" }, ais: [], databases: [] },
    }),
  );
  await page.route("**/api/system", (r) => r.fulfill({ json: { jobs: [] } }));
  for (const path of [
    "environments",
    "requests",
    "queue",
    "ticket-connectors",
    "git-connections",
  ])
    await page.route(`**/api/${path}`, (r) => r.fulfill({ json: [] }));
  await page.route("**/api/ai-connections", (r) =>
    r.fulfill({ json: [connection] }),
  );
}

test("global orchestration and cumulative connection roles preserve sparse inheritance", async ({
  page,
}) => {
  await base(page);
  let settings = structuredClone(initial);
  let settingsBody: Record<string, unknown> | null = null;
  let connectionBody: Record<string, unknown> | null = null;
  await page.route("**/api/orchestration-settings", (r) => {
    if (r.request().method() === "PUT") {
      settingsBody = r.request().postDataJSON();
      settings = { ...settings, ...settingsBody };
    }
    return r.fulfill({ json: settings });
  });
  await page.route("**/api/ai-connections/41", (r) => {
    connectionBody = r.request().postDataJSON();
    return r.fulfill({ json: connection });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "AI & Agents", exact: true }).click();
  await page.getByLabel("Verify compared analyses", { exact: true }).uncheck();
  await page.getByLabel("Maximum AI calls per analysis").fill("10");
  await page.getByLabel("Analysis time limit (seconds)").fill("200");
  await page
    .getByText("Advanced role instructions and tools", { exact: true })
    .click();
  await expect(
    page.getByRole("checkbox", {
      name: "Code inspection · Required",
      exact: true,
    }),
  ).toBeDisabled();
  await page
    .getByLabel("Analyst instructions", { exact: true })
    .fill("Check file references");
  await page.getByLabel("Evidence review", { exact: true }).check();
  await page
    .getByRole("button", { name: "Save analysis settings" })
    .click();
  await expect
    .poll(() => settingsBody)
    .toMatchObject({
      verifier_enabled: false,
      max_calls: 10,
      timeout_seconds: 200,
      role_instructions: { analyst: "Check file references" },
    });
  expect(settingsBody).not.toHaveProperty("available_agents");
  expect(settingsBody).not.toHaveProperty("available_skills");
  await page
    .getByRole("region", { name: "Team assistant", exact: true })
    .getByRole("button", { name: "Edit", exact: true })
    .click();
  await expect(page.getByLabel("Analyst", { exact: true })).toBeChecked();
  await expect(page.getByLabel("Verifier", { exact: true })).toBeChecked();
  await page.getByLabel("Counter-analyst", { exact: true }).check();
  await page
    .getByText("Connection instructions and skills", { exact: true })
    .click();
  await expect(page.getByLabel("Additional instructions")).toHaveValue(
    "Preserve compatibility",
  );
  await page
    .getByLabel("Additional instructions")
    .fill("Use precise references");
  await expect(
    page.getByRole("combobox", {
      name: "Read-only database inspection",
      exact: true,
    }),
  ).toHaveValue("disabled");
  await page
    .getByRole("combobox", {
      name: "Read-only database inspection",
      exact: true,
    })
    .selectOption("inherit");
  await page
    .getByRole("combobox", { name: "Evidence references", exact: true })
    .selectOption("disabled");
  await page
    .getByRole("button", { name: "Save connection", exact: true })
    .click();
  await expect
    .poll(() => connectionBody)
    .toMatchObject({
      roles: ["analyst", "verifier", "counter_analyst"],
      additional_instructions: "Use precise references",
      skill_overrides: { evidence: false },
    });
  expect(connectionBody).not.toHaveProperty("role_instructions");
  const nav = page.getByRole("navigation", {
    name: "Main navigation",
    exact: true,
  });
  await expect(nav.getByRole("link")).toHaveCount(3);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("French settings keep verifier policy in administration and translate public roles", async ({
  page,
}) => {
  await base(page);
  await page.route("**/api/settings", (r) =>
    r.fulfill({
      json: {
        name: "SpecHelper",
        primary_color: "#2563eb",
        short_label: "",
        allow_confrontation: true,
        language: "fr",
      },
    }),
  );
  await page.route("**/api/orchestration-settings", (r) =>
    r.fulfill({ json: initial }),
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "IA & Agents", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Configuration de l’analyse",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Vérifier les analyses confrontées", { exact: true }),
  ).toBeChecked();
  await expect(
    page.getByText(
      "La vérification par une IA ne remplace pas la validation humaine du ticket et de goal.md.",
      { exact: true },
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Nouvelle connexion IA", exact: true })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "Analyste", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "Contre-analyste", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "Vérificateur", exact: true }),
  ).toBeChecked();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("queue shows the active role and historical diversity warnings remain visible", async ({
  page,
}) => {
  await base(page);
  const warning =
    "Only one eligible model family is available. Independent sessions are used.";
  const id = "55555555-5555-4555-8555-555555555555";
  await page.route("**/api/queue", (r) =>
    r.fulfill({
      json: [
        {
          id: 1,
          kind: "ANALYZE",
          status: "RUNNING",
          title: "Export analysis",
          public_role: "counter_analyst",
          warnings: [
            {
              code: "LIMITED_DIVERSITY",
              role: "counter_analyst",
              message: warning,
            },
          ],
          assignments: [
            {
              connection_id: 41,
              connection_name: "Team assistant",
              model: "gpt-review",
              public_role: "counter_analyst",
              model_family: "openai",
            },
          ],
          href: `/requests/${id}`,
        },
      ],
    }),
  );
  await page.route(`**/api/requests/${id}`, (r) =>
    r.fulfill({
      json: {
        id,
        need: "Export analysis",
        status: "ERROR",
        language: "en",
        confrontation: true,
        environment_name: "Fixture",
        baseline: [],
        database: {},
        questions: [],
        conversation: [],
        understanding: "Export analysis",
        progress: [],
        error: "",
        attachments: [],
        ticket: null,
        markdown: null,
        latest_version: null,
        versions: [],
        messages: [],
        analysis_runs: [
          {
            number: 1,
            status: "ERROR",
            warnings: [
              {
                code: "LIMITED_DIVERSITY",
                role: "counter_analyst",
                message: warning,
              },
            ],
            steps: [
              {
                public_role: "counter_analyst",
                connection_name: "Historic assistant",
                provider: "codex",
                model: "historic-model",
                model_family: "openai",
                status: "DONE",
                conclusions: ["The export keeps its existing file format."],
              },
            ],
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  const open = page.getByRole("button", { name: "Task queue", exact: true });
  if (await open.isVisible()) await open.click();
  const queue = page.locator(".task-queue:visible");
  await expect(
    queue.locator(".queue-assignment").filter({ hasText: "Team assistant · gpt-review" }),
  ).toBeVisible();
  await expect(queue.locator(".queue-role")).toHaveText("Counter-analyst");
  await expect(queue.getByText(warning, { exact: true })).toBeVisible();
  if (await page.getByRole("dialog", { name: "Task queue" }).isVisible())
    await page.keyboard.press("Escape");
  await page.goto(`/requests/${id}`);
  await expect(
    page
      .getByText("Analysis assignment history", { exact: true })
      .locator(".."),
  ).toHaveAttribute("open", "");
  await expect(
    page.getByText(
      "Step 1 · Counter-analyst · Historic assistant · codex · historic-model · Completed",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.locator("main").getByText(warning, { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Verifiable conclusions")).toContainText(
    "The export keeps its existing file format.",
  );
});
