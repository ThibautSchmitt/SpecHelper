import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const stamp = "2026-10-23T12:00:00Z";
const proposal = {
  slug: "interservice-review",
  name: "Interservice review",
  objective: "Identify the interfaces and dependency boundaries.",
  instructions:
    "Read the supplied project context and explain the interservice dependency risks with evidence.",
  enabled: false,
  compatibility: ["codex"],
  required_capabilities: ["structured_output"],
  skills: [],
  expected_checks: ["Cite interface evidence."],
};
type Draft = {
  id: string;
  kind: "agent" | "skill";
  status: string;
  revision: number;
  connection_id: number;
  definition: typeof proposal | null;
  messages: { role: string; content: string; questions: string[] }[];
  validation: {
    valid: boolean;
    errors: string[];
    compatibility: Record<string, boolean>;
  };
  recommendations: {
    kind: string;
    slug: string;
    name: string;
    reason: string;
  }[];
  job: {
    id: number;
    status: string;
    operation: string;
    connection_name: string;
    agent: string;
    model: string;
    public_role: string;
    error: string;
  } | null;
  test_result: {
    summary: string;
    checks: string[];
    limitations: string[];
    revision: number;
  } | null;
  activated_definition: object | null;
  updated_at: string;
};
const translation = (language: "en" | "fr", key: string) =>
  (language === "fr" ? fr : en)[key as keyof typeof en] || key;
async function setup(page: Page, language: "en" | "fr") {
  await page.route("**/api/settings", (route) =>
    route.fulfill({
      json: {
        name: "SpecHelper",
        language,
        short_label: "",
        primary_color: "#2563eb",
        allow_confrontation: true,
      },
    }),
  );
  await page.route("**/api/connections", (route) =>
    route.fulfill({
      json: { github: { status: "CONNECTED" }, ais: [], databases: [] },
    }),
  );
  await page.route("**/api/environments", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/queue", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/system", (route) =>
    route.fulfill({ json: { jobs: [] } }),
  );
  await page.route("**/api/library/skill", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/library/agent", (route) =>
    route.fulfill({ json: [] }),
  );
}
for (const language of ["en", "fr"] as const) {
  test(`actual library queue stages and interruption messages translate in ${language}`, async ({
    page,
  }, info) => {
    await setup(page, language);
    const t = (key: string) => translation(language, key);
    const scenarios = [
      ["RUNNING", "generate", "Preparing a library proposal"],
      ["RUNNING", "test", "Testing the draft in a sandbox"],
      ["QUEUED", "generate", "Waiting for the selected AI connection"],
      ["DONE", "generate", "Library proposal ready for review"],
      ["DONE", "test", "Sandbox demonstration completed"],
      [
        "ERROR",
        "generate",
        "Assistant work interrupted. Check the selected connection and retry.",
      ],
      ["ERROR", "test", "Worker interrupted; assistant work unfinished."],
      ["ERROR", "test", "The assistant time limit was reached."],
    ];
    await page.route("**/api/queue", (route) =>
      route.fulfill({
        json: scenarios.map(([status, operation, stage], index) => ({
          id: index + 91,
          kind: "library_assistant",
          status,
          queue_state: status,
          title: `Creation task ${index + 1}`,
          environment_name: "",
          operation:
            operation === "test"
              ? "Library sandbox test"
              : "Library generation",
          stage: status === "ERROR" ? "" : stage,
          agent: "codex",
          assignments: [
            {
              connection_id: 1,
              connection_name: "ChatGPT",
              agent: "codex",
              model: "recorded-test-model",
              public_role:
                operation === "test" ? "library_test" : "library_generator",
            },
          ],
          assignment_state: status === "RUNNING" ? "current" : "previous",
          request_status: status,
          queue_position: status === "QUEUED" ? 1 : null,
          created_at: stamp,
          started_at: null,
          finished_at: null,
          error: status === "ERROR" ? stage : "",
          href: "/admin",
        })),
      }),
    );
    await page.goto("/admin");
    const mobile = info.project.name === "mobile";
    if (mobile)
      await page
        .getByRole("button", { name: t("Task queue"), exact: true })
        .click();
    const queue = page.getByRole(mobile ? "dialog" : "complementary", {
      name: t("Task queue"),
      exact: true,
    });
    for (const [index, [status, operation, stage]] of scenarios.entries()) {
      const card = queue.locator(`[data-job="${index + 91}"]`);
      await expect(card.locator(".queue-description")).toHaveText(t(stage));
      await expect(card.locator(".queue-role")).toHaveText(
        t(
          operation === "test"
            ? "Definition sandbox test"
            : "Definition generator",
        ),
      );
      if (status !== "QUEUED")
        await expect(card.locator(".queue-context")).toHaveText(
          t(
            operation === "test"
              ? "Library sandbox test"
              : "Library generation",
          ),
        );
      if (language === "fr") expect(t(stage)).not.toBe(stage);
    }
  });

  test(`creation discussion, sandbox queue and human activation stay distinct in ${language}`, async ({
    page,
  }, info) => {
    await setup(page, language);
    const t = (key: string) => translation(language, key);
    const errors: string[] = [];
    page.on("pageerror", (value) => errors.push(value.message));
    let value: Draft | null = null;
    let generation = 0;
    let activations = 0;
    let saves = 0;
    let conflict = false;
    let finishTest = false;
    await page.route("**/api/library-assistant/drafts**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const payload = request.postDataJSON();
      if (
        request.method() === "GET" &&
        url.pathname === "/api/library-assistant/drafts"
      )
        return route.fulfill({ json: value ? [value] : [] });
      if (
        request.method() === "POST" &&
        url.pathname === "/api/library-assistant/drafts"
      ) {
        expect(payload).toMatchObject({
          kind: "agent",
          connection_id: 1,
          language,
          description: "Review interservice dependencies.",
        });
        value = {
          id: "draft-1",
          kind: "agent",
          status: "DRAFT",
          revision: 1,
          connection_id: 1,
          definition: null,
          messages: [
            { role: "user", content: payload.description, questions: [] },
          ],
          validation: { valid: false, errors: [], compatibility: {} },
          recommendations: [],
          job: {
            id: 81,
            status: "QUEUED",
            operation: "generate",
            connection_name: "ChatGPT",
            agent: "codex",
            model: "recorded-test-model",
            public_role: "library_generator",
            error: "",
          },
          test_result: null,
          activated_definition: null,
          updated_at: stamp,
        };
        return route.fulfill({ json: value });
      }
      if (!value) throw new Error("No draft exists");
      if (request.method() === "GET") {
        if (
          value.job?.status === "QUEUED" &&
          value.job.operation === "generate"
        ) {
          value.job.status = "DONE";
          value.revision++;
          if (generation === 0) {
            value.status = "NEEDS_CLARIFICATION";
            value.messages.push({
              role: "assistant",
              content: "I need one detail.",
              questions: ["Which interface should the review focus on?"],
            });
          } else {
            value.status = "PROPOSED";
            value.definition = structuredClone(proposal);
            value.validation = {
              valid: true,
              errors: [],
              compatibility: { codex: true, claude: false },
            };
            value.messages.push({
              role: "assistant",
              content: "Here is an editable proposal.",
              questions: [],
            });
            value.recommendations = [
              {
                kind: "agent",
                slug: "code",
                name: "Source analysis",
                reason:
                  "An existing source analyst can cover basic dependency discovery.",
              },
            ];
          }
        }
        if (value.job?.operation === "test" && finishTest) {
          value.job.status = "DONE";
          value.test_result = {
            summary: "The demonstration was reviewed without changes.",
            checks: ["Interface evidence included."],
            limitations: ["Synthetic demonstration only."],
            revision: value.revision,
          };
        }
        return route.fulfill({ json: value });
      }
      expect(payload.expected_revision).toBe(value.revision);
      if (url.pathname.endsWith("/messages")) {
        expect(payload.message).toBe("Focus on the billing event interface.");
        generation++;
        value.messages.push({
          role: "user",
          content: payload.message,
          questions: [],
        });
        value.revision++;
        value.job = {
          ...value.job!,
          id: 82,
          status: "QUEUED",
          operation: "generate",
        };
        return route.fulfill({ json: value });
      }
      if (request.method() === "PUT") {
        if (conflict) {
          conflict = false;
          return route.fulfill({
            status: 409,
            json: { detail: "The draft has changed. Refresh before editing." },
          });
        }
        saves++;
        expect(payload.definition.enabled).toBe(false);
        value.definition = payload.definition;
        value.revision++;
        value.validation = {
          valid: true,
          errors: [],
          compatibility: { codex: true, claude: false },
        };
        return route.fulfill({ json: value });
      }
      if (url.pathname.endsWith("/test")) {
        expect(payload.demo).toBe(
          "Explain the billing service event dependencies.",
        );
        value.job = {
          ...value.job!,
          id: 83,
          status: "QUEUED",
          operation: "test",
          public_role: "library_test",
        };
        return route.fulfill({ json: value });
      }
      if (url.pathname.endsWith("/activate")) {
        activations++;
        expect(value.job?.status).toBe("DONE");
        value.status = "ACTIVE";
        value.revision++;
        value.activated_definition = {
          ...value.definition,
          enabled: true,
          version: 1,
        };
        return route.fulfill({ json: value });
      }
      throw new Error(`Unexpected assistant request ${url.pathname}`);
    });
    await page.route("**/api/queue", (route) =>
      route.fulfill({
        json:
          value?.job?.operation === "test"
            ? [
                {
                  id: 83,
                  kind: "library_assistant",
                  status: value.job.status,
                  queue_state: value.job.status,
                  title: "Interservice review",
                  environment_name: "",
                  operation: "Library sandbox test",
                  stage:
                    value.job.status === "DONE"
                      ? "Sandbox demonstration completed"
                      : "Waiting for the selected AI connection",
                  agent: "codex",
                  public_role: "library_test",
                  assignments: [
                    {
                      connection_id: 1,
                      connection_name: "ChatGPT",
                      agent: "codex",
                      model: "recorded-test-model",
                      public_role: "library_test",
                    },
                  ],
                  assignment_state: "current",
                  request_status: value.job.status,
                  queue_position: 1,
                  created_at: stamp,
                  started_at: null,
                  finished_at: null,
                  error: "",
                  href: "/admin?library_draft=draft-1&library_kind=agent",
                },
              ]
            : [],
      }),
    );
    await page.goto("/admin");
    await page
      .getByRole("button", { name: t("AI & Agents"), exact: true })
      .click();
    await page
      .getByRole("navigation", { name: t("AI settings"), exact: true })
      .getByRole("button", { name: t("Agents"), exact: true })
      .click();
    await page
      .getByRole("button", { name: t("Generate an agent"), exact: true })
      .click();
    const assistant = page.getByRole("region", {
      name: t("Creation assistant"),
      exact: true,
    });
    await assistant
      .getByLabel(t("What should this definition help with?"), { exact: true })
      .fill("Review interservice dependencies.");
    await assistant
      .getByRole("button", { name: t("Start generation"), exact: true })
      .click();
    await expect(assistant).toContainText(
      "Which interface should the review focus on?",
      { timeout: 6000 },
    );
    expect(activations).toBe(0);
    await assistant
      .getByLabel(t("Answer or request a revision"), { exact: true })
      .fill("Focus on the billing event interface.");
    await assistant
      .getByRole("button", { name: t("Revise"), exact: true })
      .click();
    await expect(
      assistant.getByLabel(t("Instructions"), { exact: true }),
    ).toHaveValue(proposal.instructions, { timeout: 6000 });
    await expect(assistant).toContainText(
      "An existing source analyst can cover basic dependency discovery.",
    );
    await assistant
      .getByLabel(t("Instructions"), { exact: true })
      .fill("Explain the interface ownership and cite the supplied evidence.");
    const comparison = assistant.locator("details").filter({
      has: page.locator("summary", { hasText: t("Review changes") }),
    });
    await comparison.locator("summary").click();
    await expect(comparison).toContainText(proposal.instructions);
    await expect(comparison).toContainText(
      "Explain the interface ownership and cite the supplied evidence.",
    );
    await expect(comparison.locator("pre")).toHaveCount(0);
    await expect(
      assistant.getByRole("button", { name: t("Activate"), exact: true }),
    ).toBeDisabled();
    await expect(
      assistant.getByRole("button", {
        name: t("Test in a sandbox"),
        exact: true,
      }),
    ).toBeDisabled();
    conflict = true;
    await assistant
      .getByRole("button", { name: t("Save as draft"), exact: true })
      .click();
    await expect(assistant.getByRole("alert")).toContainText(
      t("The draft has changed. Refresh before editing."),
    );
    await expect(
      assistant.getByLabel(t("Instructions"), { exact: true }),
    ).toHaveValue(
      "Explain the interface ownership and cite the supplied evidence.",
    );
    await assistant
      .getByRole("button", { name: t("Save as draft"), exact: true })
      .click();
    expect(saves).toBe(1);
    expect(activations).toBe(0);
    await assistant
      .getByLabel(t("Demonstration request"), { exact: true })
      .fill("Explain the billing service event dependencies.");
    await assistant
      .getByRole("button", { name: t("Test in a sandbox"), exact: true })
      .click();
    await expect(
      assistant.getByRole("status", { name: t("Assistant task") }),
    ).toContainText("recorded-test-model");
    await expect(
      assistant.getByRole("status", { name: t("Assistant task") }),
    ).toContainText(t("Definition sandbox test"));
    const mobile = info.project.name === "mobile";
    if (mobile)
      await page
        .getByRole("button", { name: t("Task queue"), exact: true })
        .click();
    const queue = page.getByRole(mobile ? "dialog" : "complementary", {
      name: t("Task queue"),
      exact: true,
    });
    await expect(queue.locator('[data-job="83"]')).toContainText(
      t("Definition sandbox test"),
      { timeout: 6500 },
    );
    await expect(
      queue.locator('[data-job="83"] .queue-description'),
    ).toHaveText(t("Waiting for the selected AI connection"));
    await expect(queue.locator('[data-job="83"] .queue-model')).toHaveText(
      "recorded-test-model",
    );
    await queue.locator('[data-job="83"] a').click();
    await expect(page).toHaveURL(/library_draft=draft-1/);
    if (mobile) await expect(queue).not.toBeVisible();
    await expect(assistant.getByLabel(t("Name"), { exact: true })).toHaveValue(
      "Interservice review",
    );
    finishTest = true;
    await expect(
      assistant.getByRole("region", {
        name: t("Sandbox test result"),
        exact: true,
      }),
    ).toContainText("The demonstration was reviewed without changes.", {
      timeout: 6000,
    });
    expect(activations).toBe(0);
    await assistant
      .getByRole("button", { name: t("Activate"), exact: true })
      .click();
    expect(activations).toBe(0);
    await assistant
      .getByRole("group", { name: t("Confirm activation"), exact: true })
      .getByRole("button", { name: t("Confirm activation"), exact: true })
      .click();
    await expect(assistant).toContainText(
      t("Definition activated in the shared library."),
    );
    expect(activations).toBe(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
    await page.screenshot({
      path: `../.local/v21-evidence/assistant-${language}-${info.project.name}.png`,
      fullPage: true,
    });
  });

  test(`skill draft resume, validated import and historical restoration in ${language}`, async ({
    page,
  }) => {
    await setup(page, language);
    const t = (key: string) => translation(language, key);
    const saved = {
      ...proposal,
      slug: "review-skill",
      name: "Review skill",
      version: 2,
      deleted: false,
    };
    let skills = [saved];
    let restores = 0;
    let imports = 0;
    await page.route("**/api/library/skill", (route) =>
      route.fulfill({ json: skills }),
    );
    await page.route("**/api/library/skill/review-skill/versions", (route) =>
      route.fulfill({
        json: [
          {
            version: 2,
            definition: saved,
            action: "edited",
            editor: "session:example",
            created_at: stamp,
          },
          {
            version: 1,
            definition: {
              ...saved,
              version: 1,
              instructions: "Original instructions.",
            },
            action: "created",
            editor: "session:example",
            created_at: stamp,
          },
        ],
      }),
    );
    await page.route(
      "**/api/library/skill/review-skill/restore",
      async (route) => {
        expect(route.request().postDataJSON()).toEqual({
          version: 1,
          expected_version: 2,
        });
        restores++;
        skills = [
          {
            ...saved,
            version: 3,
            instructions: "Original instructions.",
            enabled: false,
          },
        ];
        return route.fulfill({ json: skills[0] });
      },
    );
    let invalidImport = true;
    await page.route("**/api/library/import/preview", (route) =>
      route.fulfill({
        json: {
          valid: !invalidImport,
          errors: invalidImport ? ["Invalid field: expected_checks.0"] : [],
          definition: invalidImport ? null : proposal,
          compatibility: { codex: true, claude: false },
          activation_required: true,
        },
      }),
    );
    await page.route("**/api/library/import", (route) => {
      expect(route.request().postDataJSON()).toEqual({
        schema_version: 1,
        kind: "skill",
        definition: proposal,
      });
      imports++;
      return route.fulfill({
        json: { ...proposal, version: 1, enabled: false },
      });
    });
    const draft: Draft = {
      id: "saved-skill",
      kind: "skill",
      status: "PROPOSED",
      revision: 4,
      connection_id: 1,
      definition: { ...proposal, slug: "resume-skill", name: "Resume skill" },
      messages: [
        { role: "user", content: "Prepare a review skill.", questions: [] },
      ],
      validation: { valid: true, errors: [], compatibility: { codex: true } },
      recommendations: [],
      job: null,
      test_result: null,
      activated_definition: null,
      updated_at: stamp,
    };
    await page.route("**/api/library-assistant/drafts", (route) =>
      route.fulfill({ json: [draft] }),
    );
    await page.route(
      "**/api/library-assistant/drafts/saved-skill/cancel",
      (route) => {
        expect(route.request().postDataJSON()).toEqual({
          expected_revision: 4,
        });
        return route.fulfill({
          json: { ...draft, status: "CANCELLED", revision: 5 },
        });
      },
    );
    await page.goto("/admin?library_draft=saved-skill&library_kind=skill");
    const assistant = page.getByRole("region", {
      name: t("Creation assistant"),
      exact: true,
    });
    await expect(assistant.getByLabel(t("Name"), { exact: true })).toHaveValue(
      "Resume skill",
    );
    await assistant
      .getByRole("button", { name: t("Cancel creation"), exact: true })
      .click();
    await expect(assistant).toContainText(
      t("Creation cancelled. No definition was activated."),
    );
    await assistant
      .getByRole("button", { name: t("Close"), exact: true })
      .click();
    await page
      .getByRole("button", {
        name: t("Versions of {name}").replace("{name}", "Review skill"),
        exact: true,
      })
      .click();
    await page
      .locator("details")
      .filter({ has: page.locator("summary", { hasText: /^v1/ }) })
      .locator("summary")
      .click();
    await page
      .getByRole("button", {
        name: t("Restore version {version}").replace("{version}", "1"),
        exact: true,
      })
      .click();
    expect(restores).toBe(0);
    await page
      .getByRole("group", { name: t("Confirm restoration"), exact: true })
      .getByRole("button", { name: t("Confirm restoration"), exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: /^Review skill v/ }),
    ).toContainText("v3");
    expect(restores).toBe(1);
    await page
      .getByRole("button", { name: t("Import definition"), exact: true })
      .click();
    await page.getByLabel(t("Definition JSON"), { exact: true }).fill(
      JSON.stringify({
        schema_version: 1,
        kind: "skill",
        definition: proposal,
      }),
    );
    await expect(
      page.getByRole("button", { name: t("Import as draft"), exact: true }),
    ).toBeDisabled();
    await page
      .getByRole("button", { name: t("Validate import"), exact: true })
      .click();
    const importer = page.getByRole("region", {
      name: t("Import definition"),
      exact: true,
    });
    await expect(importer.getByRole("status")).toContainText(
      language === "fr"
        ? "Vérifiez le champ Vérifications attendues, élément 1."
        : "Check the Expected checks, item 1 field.",
    );
    await expect(importer.getByRole("status")).not.toContainText("expected_checks");
    await expect(
      page.getByRole("button", { name: t("Import as draft"), exact: true }),
    ).toBeDisabled();
    invalidImport = false;
    await page
      .getByRole("button", { name: t("Validate import"), exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: t("Import as draft"), exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: t("Import as draft"), exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText(
      t("Definition imported as an inactive draft."),
    );
    expect(imports).toBe(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}
