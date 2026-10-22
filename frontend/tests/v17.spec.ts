import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const id = "77777777-7777-4777-8777-777777777777";
const createdId = "88888888-8888-4888-8888-888888888888";
const timestamp = "2026-10-22T12:00:00Z";
const environments = [
  { id: 91, name: "Production", status: "READY", repositories: [] },
  { id: 92, name: "Staging", status: "READY", repositories: [] },
];
const answer = (number: number) =>
  `# Contract validation v${number}\n\n## Verified facts\n\nThe Java service checks status ${number}.\n\n## Source references\n\n- project/api \`src/Contract.java\` · \`validate\` · release · \`${String(number).repeat(40)}\`\n\n## Uncertainties\n\nHistorical imports were not checked.`;
const version = (number: number) => ({
  id: `version-${number}`,
  number,
  run_number: number,
  format_version: "question-1.0",
  language: "en",
  status: "READY",
  created_at: timestamp,
  explanation: { title: `Contract validation v${number}` },
  answer_markdown: answer(number),
  markdown: answer(number),
  artifacts: {
    "answer.md": `/api/questions/${id}/versions/${number}/artifacts/answer.md`,
  },
});
const detail = (status = "READY") => ({
  id,
  workflow: "question",
  title: "Contract validation v2",
  need: "How are contracts validated?",
  environment_id: 91,
  environment_name: "Production",
  status,
  language: "en",
  confrontation: false,
  created_at: timestamp,
  updated_at: timestamp,
  baseline: [
    { repository: "project/api", branch: "release", sha: "2".repeat(40) },
  ],
  database: {},
  questions: [],
  conversation: [],
  understanding: "Explain existing validation",
  progress: [],
  error: "",
  attachments: [{ id: "screenshot", name: "contract.png", size: 10 }],
  latest_version: version(2),
  versions: [
    { number: 1, created_at: timestamp },
    { number: 2, created_at: timestamp },
  ],
  messages: [
    {
      id: 1,
      role: "user",
      kind: "followup",
      content: "What about imported records?",
      version_number: null,
    },
  ],
  analysis_runs: [],
  derived_requests: [
    {
      id: createdId,
      need: "Add a validation reminder",
      status: "READY",
      source_version: 1,
    },
  ],
});
async function base(page: Page, language = "en") {
  await page.route("**/api/settings", (r) =>
    r.fulfill({
      json: {
        name: "SpecHelper",
        primary_color: "#2563eb",
        short_label: "",
        allow_confrontation: true,
        language,
      },
    }),
  );
  await page.route("**/api/environments", (r) =>
    r.fulfill({ json: environments }),
  );
  await page.route("**/api/requests", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/questions", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/queue", (r) => r.fulfill({ json: [] }));
}
async function question(page: Page) {
  await base(page);
  await page.route(`**/api/questions/${id}`, (r) =>
    r.fulfill({ json: detail() }),
  );
  await page.route(`**/api/questions/${id}/versions/1`, (r) =>
    r.fulfill({ json: version(1) }),
  );
  await page.route(`**/api/questions/${id}/versions/*/documents`, (r) =>
    r.fulfill({ json: [] }),
  );
}

test("Questions uses the shared navigation, queue and creation form with optional files and comparison", async ({
  page,
}) => {
  await base(page);
  const calls: string[] = [];
  await page.route("**/api/questions", async (r) => {
    if (r.request().method() === "GET")
      return r.fulfill({
        json: [{ ...detail(), title: "Existing contract checks" }],
      });
    expect(r.request().postDataJSON()).toEqual({
      environment_id: 91,
      need: "How does contract validation work?",
      category: "general",
    });
    calls.push("create");
    return r.fulfill({ json: { id } });
  });
  await page.route(`**/api/questions/${id}`, (r) =>
    r.fulfill({
      json: {
        ...detail("QUEUED"),
        latest_version: null,
        versions: [],
        derived_requests: [],
      },
    }),
  );
  await page.route(`**/api/questions/${id}/attachments`, (r) => {
    calls.push("attachment");
    expect(r.request().postDataBuffer()?.toString()).toContain("contracts.md");
    return r.fulfill({ json: {} });
  });
  await page.route(`**/api/questions/${id}/analyze`, (r) => {
    calls.push("analyze");
    return r.fulfill({ json: {} });
  });
  await page.route("**/api/queue", (r) =>
    r.fulfill({
      json: [
        {
          id: 7,
          workflow: "question",
          kind: "analysis",
          title: "Existing contract checks",
          environment_name: "Production",
          operation: "Question analysis",
          status: "RUNNING",
          request_status: "ANALYZING",
          href: `/questions/${id}`,
          created_at: timestamp,
          queue_position: null,
          started_at: null,
          assignments: [
            {
              connection_id: 1,
              connection_name: "ChatGPT",
              model: "gpt-example",
              public_role: "analyst",
            },
          ],
        },
      ],
    }),
  );
  await page.goto("/questions");
  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await expect(
    navigation.getByRole("link", { name: "Questions", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(navigation.getByRole("link")).toHaveText([
    "Requests",
    "Questions",
    "Tickets",
  ]);
  await expect(
    page.getByRole("link", { name: /Existing contract checks/ }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Last updated", { exact: false }).first(),
  ).toBeVisible();
  await page.getByLabel("Environment", { exact: true }).selectOption("91");
  await page
    .getByLabel("Your question", { exact: true })
    .fill("How does contract validation work?");
  await page
    .getByLabel("Attachments", { exact: false })
    .setInputFiles({
      name: "contracts.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("Describe validation"),
    });
  await expect(
    page.getByLabel("Compare multiple analyses", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Analyze question", exact: true })
    .click();
  await expect(page).toHaveURL(`/questions/${id}`);
  await expect(
    page.getByRole("heading", { name: "Your question is queued", exact: true }),
  ).toBeVisible();
  expect(calls).toEqual(["create", "attachment", "analyze"]);
  if (test.info().project.name === "mobile")
    await page.getByRole("button", { name: "Task queue", exact: true }).click();
  const queue = page.getByRole(
    test.info().project.name === "mobile" ? "dialog" : "complementary",
    { name: "Task queue", exact: true },
  );
  await expect(queue.getByText("Question", { exact: true })).toBeVisible();
  await expect(
    queue.getByText("ChatGPT · gpt-example", { exact: false }),
  ).toBeVisible();
});

test("copy and download use exactly the displayed historical explanation with no ticket or goal actions", async ({
  page,
}) => {
  await question(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: async (text: string) => {
          (window as Window & { copied?: string }).copied = text;
        },
      },
    });
  });
  await page.goto(`/questions/${id}?version=1`);
  await expect(
    page
      .getByRole("heading", { name: "Contract validation v1", exact: true })
      .first(),
  ).toBeVisible();
  await expect(page.getByTestId("question-explanation")).toContainText(
    "src/Contract.java",
  );
  await expect(page.getByTestId("question-explanation")).toContainText(
    "1".repeat(40),
  );
  await page
    .getByRole("button", { name: "Copy explanation", exact: true })
    .click();
  expect(
    await page.evaluate(() => (window as Window & { copied?: string }).copied),
  ).toBe(answer(1));
  await expect(
    page.getByRole("link", { name: "Download explanation", exact: true }),
  ).toHaveAttribute(
    "href",
    `/api/questions/${id}/versions/1/artifacts/answer.md`,
  );
  await expect(
    page.getByRole("link", { name: "Create a request", exact: true }),
  ).toHaveAttribute("href", `/?from_question=${id}&version=1`);
  await expect(
    page.getByRole("button", { name: "Copy for Jira", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("goal.md", { exact: true })).toHaveCount(0);
  await page.screenshot({
    path: `../.local/screenshots/v17-question-${test.info().project.name}.png`,
    fullPage: true,
  });
  await page
    .getByLabel("Result version", { exact: true })
    .selectOption("latest");
  await expect(
    page
      .getByRole("heading", { name: "Contract validation v2", exact: true })
      .first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Copy explanation", exact: true })
    .click();
  expect(
    await page.evaluate(() => (window as Window & { copied?: string }).copied),
  ).toBe(answer(2));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("all documentation formats stay linked to the selected answer version", async ({
  page,
}) => {
  await question(page);
  const kinds: string[] = [];
  await page.route(`**/api/questions/${id}/versions/1/documents`, (r) => {
    if (r.request().method() === "GET") return r.fulfill({ json: [] });
    const { kind } = r.request().postDataJSON();
    kinds.push(kind);
    return r.fulfill({
      status: 201,
      json: {
        id: `doc-${kind}`,
        kind,
        source_version: 1,
        language: "en",
        created_at: timestamp,
        markdown: `# ${kind}\n\nSource: v1 with verified source references.`,
        download_url: `/api/questions/${id}/versions/1/documents/doc-${kind}/download`,
      },
    });
  });
  await page.goto(`/questions/${id}?version=1`);
  for (const kind of ["business", "technical", "mixed"]) {
    await page
      .getByLabel("Documentation format", { exact: true })
      .selectOption(kind);
    await page
      .getByRole("button", { name: "Generate documentation", exact: true })
      .click();
    await expect(
      page.getByRole("link", { name: "Download documentation", exact: true }),
    ).toHaveCount(kinds.length);
  }
  expect(kinds).toEqual(["business", "technical", "mixed"]);
  await expect(
    page.getByText("Source answer version 1", { exact: false }),
  ).toHaveCount(3);
  await page
    .getByText("Preview documentation", { exact: true })
    .first()
    .click();
  await expect(
    page
      .getByText("Source: v1 with verified source references.", { exact: true })
      .first(),
  ).toBeVisible();
  await page
    .getByLabel("Result version", { exact: true })
    .selectOption("latest");
  await expect(
    page
      .getByRole("heading", { name: "Contract validation v2", exact: true })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download documentation", exact: true }),
  ).toHaveCount(0);
});

test("questions reuse clarifications and followup conversation without losing old results", async ({
  page,
}) => {
  await question(page);
  let state = {
    ...detail("NEEDS_CLARIFICATION"),
    questions: [{ id: "scope", question: "Which contract types?" }],
  };
  await page.route(`**/api/questions/${id}`, (r) => r.fulfill({ json: state }));
  await page.route(`**/api/questions/${id}/answers`, (r) => {
    expect(r.request().postDataJSON()).toEqual({
      answers: { scope: "All active contracts" },
    });
    state = { ...detail(), questions: [] };
    return r.fulfill({ json: state });
  });
  await page.route(`**/api/questions/${id}/continue`, (r) => {
    expect(r.request().postDataJSON()).toEqual({
      message: "Explain imports too",
      expected_version: 2,
    });
    return r.fulfill({ json: detail("CONTINUING_CONVERSATION") });
  });
  await page.goto(`/questions/${id}`);
  await page
    .getByLabel("Which contract types?", { exact: true })
    .fill("All active contracts");
  await page
    .getByRole("button", { name: "Answer and continue", exact: true })
    .click();
  await page.getByText("Discussion history", { exact: true }).click();
  await expect(
    page.getByText("What about imported records?", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Add a validation reminder", exact: true }),
  ).toHaveAttribute("href", `/requests/${createdId}`);
  await page
    .getByRole("button", { name: "Continue the discussion", exact: true })
    .click();
  await page
    .getByLabel("Your message", { exact: true })
    .fill("Explain imports too");
  await page
    .getByRole("button", { name: "Send and update explanation", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your question is queued", exact: true }),
  ).toBeVisible();
});

for (const includeContext of [true, false])
  test(`question handoff requires an explicit need, allows a new environment and ${includeContext ? "keeps" : "removes"} context`, async ({
    page,
  }) => {
    await base(page);
    const submitted: Record<string, unknown>[] = [];
    await page.route(`**/api/questions/${id}/versions/1/transfer`, (r) =>
      r.fulfill({
        json: {
          name: "question-context.md",
          content:
            "# Validation context\n\nVerified rule; assumption remains unconfirmed.\nSource question v1; SHA abcdef.",
          source_question_id: id,
          source_version: 1,
          environment_id: 91,
          baseline: [],
          language: "en",
        },
      }),
    );
    await page.route(`**/api/questions/${id}/requests`, (r) => {
      submitted.push(r.request().postDataJSON());
      return r.fulfill({ json: { id: createdId } });
    });
    await page.route(`**/api/requests/${createdId}/analyze`, (r) =>
      r.fulfill({ json: {} }),
    );
    await page.route(`**/api/requests/${createdId}`, (r) =>
      r.fulfill({
        json: {
          ...detail("QUEUED"),
          workflow: "request",
          id: createdId,
          source_question: { id, version: 1 },
          need: "Add a validation reminder",
          latest_version: null,
          versions: [],
          derived_requests: [],
        },
      }),
    );
    await page.goto(`/?from_question=${id}&version=1`);
    await expect(page.getByLabel("Environment", { exact: true })).toHaveValue(
      "91",
    );
    await expect(
      page.getByLabel("Describe your need", { exact: true }),
    ).toHaveValue("");
    await page
      .getByRole("button", { name: "Analyze request", exact: true })
      .click();
    expect(submitted).toHaveLength(0);
    await page.getByText("Review transferred context", { exact: true }).click();
    await expect(
      page.getByText("Verified rule; assumption remains unconfirmed.", {
        exact: false,
      }),
    ).toBeVisible();
    await page.getByLabel("Environment", { exact: true }).selectOption("92");
    if (!includeContext)
      await page
        .getByLabel("Attach question context", { exact: false })
        .uncheck();
    await page
      .getByLabel("Describe your need", { exact: true })
      .fill("Add a validation reminder");
    await page
      .getByRole("button", { name: "Analyze request", exact: true })
      .click();
    await expect(page).toHaveURL(`/requests/${createdId}`);
    expect(submitted).toEqual([
      {
        environment_id: 92,
        need: "Add a validation reminder",
        category: "auto",
        source_version: 1,
        include_context: includeContext,
      },
    ]);
    await expect(
      page.getByRole("link", { name: "Question · Version 1", exact: true }),
    ).toHaveAttribute("href", `/questions/${id}?version=1`);
  });

test("French questions and documentation controls are translated", async ({
  page,
}) => {
  await question(page);
  await page.route("**/api/settings", (r) =>
    r.fulfill({
      json: {
        name: "SpecHelper",
        primary_color: "#2563eb",
        language: "fr",
        allow_confrontation: true,
      },
    }),
  );
  await page.goto(`/questions/${id}`);
  await expect(
    page.getByRole("button", { name: "Copier l’explication", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Créer une demande", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Format de documentation", { exact: true }),
  ).toHaveText(
    "Documentation métierDocumentation techniqueDocumentation mixte",
  );
  await page
    .getByRole("link", { name: "Toutes les questions", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Nouvelle question", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Votre question", { exact: true }),
  ).toBeVisible();
});
