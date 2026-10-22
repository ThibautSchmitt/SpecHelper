import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
const git = [
  {
    id: 10,
    name: "Personal GitHub",
    provider: "github",
    base_url: "https://github.com",
    enabled: true,
    status: "CONNECTED",
    account: "alex",
    referenced_environments: 1,
  },
  {
    id: 20,
    name: "GitLab cloud",
    provider: "gitlab",
    base_url: "https://gitlab.com",
    enabled: true,
    status: "CONNECTED",
    account: "team",
    referenced_environments: 0,
  },
  {
    id: 30,
    name: "GitLab internal",
    provider: "gitlab",
    base_url: "https://git.example.test",
    enabled: true,
    status: "CONNECTED",
    account: "internal",
    referenced_environments: 1,
  },
];
const ai = [
  {
    id: 11,
    name: "Primary coding",
    agent: "codex",
    model: "gpt-example",
    identity_id: "account-a",
    quota_identity_id: "shared-a",
    account: "team@example.test",
    enabled: true,
    status: "CONNECTED",
    availability: "AVAILABLE",
    quota_windows: {},
  },
  {
    id: 12,
    name: "Careful review",
    agent: "codex",
    model: "gpt-review",
    identity_id: "account-b",
    quota_identity_id: "shared-a",
    account: "team@example.test",
    enabled: true,
    status: "CONNECTED",
    availability: "AVAILABLE",
    quota_windows: {},
  },
  {
    id: 13,
    name: "Claude backup",
    agent: "claude",
    model: "sonnet",
    identity_id: "account-c",
    quota_identity_id: "account-c",
    account: "backup@example.test",
    enabled: true,
    status: "CONNECTED",
    availability: "QUOTA_EXHAUSTED",
    quota_windows: { weekly: { exhausted: true } },
  },
];
async function base(page: Page) {
  await page.route("**/api/connections", (r) =>
    r.fulfill({
      json: { github: { status: "CONNECTED" }, ais: [], databases: [] },
    }),
  );
  await page.route("**/api/system", (r) => r.fulfill({ json: { jobs: [] } }));
  await page.route("**/api/environments", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/requests", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/queue", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/ticket-connectors", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/git-connections", (r) => r.fulfill({ json: git }));
  await page.route("**/api/ai-connections", (r) => r.fulfill({ json: ai }));
}

test("mixed Git sources preserve fork identity, reset dependent selections and reject exact duplicates", async ({
  page,
}) => {
  await base(page);
  const queries: string[] = [];
  await page.route("**/api/git-connections/*/projects?**", (r) => {
    const url = new URL(r.request().url());
    queries.push(url.href);
    const source = Number(url.pathname.split("/")[3]);
    const second = url.searchParams.get("page") === "2";
    return r.fulfill({
      json: {
        items: [
          {
            id: `${source}${second ? "2" : "1"}`,
            remote_id: `${source}${second ? "2" : "1"}`,
            path: second ? "team/fork" : `team/app-${source}`,
            default_branch: "main",
            is_fork: second,
            parent: second
              ? { path: "upstream/app", url: "https://github.com/upstream/app" }
              : null,
          },
        ],
        has_more: !second,
      },
    });
  });
  await page.route("**/api/git-connections/*/branches?**", (r) =>
    r.fulfill({
      json: {
        items: [
          { name: "main", sha: "a".repeat(40) },
          { name: "release", sha: "b".repeat(40) },
        ],
        has_more: false,
      },
    }),
  );
  let saved: Record<string, unknown> | null = null;
  await page.route("**/api/environments", (r) =>
    r.request().method() === "POST"
      ? ((saved = r.request().postDataJSON()), r.fulfill({ json: { id: 1 } }))
      : r.fulfill({ json: [] }),
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  await page.locator("#env-name").fill("Mixed sources");
  await page.locator("#new-source-0-connection").selectOption("10");
  await expect(page.locator("#new-source-0-repository option")).toHaveText([
    "Choose a project",
    "team/app-10",
  ]);
  await page
    .getByRole("button", { name: "More projects", exact: true })
    .click();
  await page.locator("#new-source-0-repository").selectOption("102");
  await expect(
    page.getByText("Fork · Parent repository: upstream/app", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("#new-source-0-branch option")).toHaveText([
    "Choose a version",
    "main",
    "release",
  ]);
  await page.locator("#new-source-0-branch").selectOption("release");
  await page
    .getByRole("button", { name: "Add a project", exact: true })
    .click();
  await page.locator("#new-source-1-connection").selectOption("20");
  await page.locator("#new-source-1-search").fill("app");
  await expect
    .poll(() => queries.some((q) => q.includes("search=app")))
    .toBe(true);
  await page.locator("#new-source-1-repository").selectOption("201");
  await expect(page.locator("#new-source-1-branch option")).toHaveCount(3);
  await page.locator("#new-source-1-branch").selectOption("main");
  await page.locator("#new-source-1-connection").selectOption("30");
  await expect(page.locator("#new-source-1-repository")).toHaveValue("");
  await expect(page.locator("#new-source-1-branch")).toHaveValue("");
  await page.locator("#new-source-1-repository").selectOption("301");
  await expect(page.locator("#new-source-1-branch option")).toHaveCount(3);
  await page.locator("#new-source-1-branch").selectOption("main");
  await page
    .getByRole("button", { name: "Add a project", exact: true })
    .click();
  await page.locator("#new-source-2-connection").selectOption("30");
  await page.locator("#new-source-2-repository").selectOption("301");
  await expect(page.locator("#new-source-2-branch option")).toHaveCount(3);
  await page.locator("#new-source-2-branch").selectOption("main");
  await expect(
    page.getByText(
      "This connection, project and branch are already selected.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create environment", exact: true }),
  ).toBeDisabled();
  await page.locator("#new-source-2-connection").selectOption("20");
  await page.locator("#new-source-2-repository").selectOption("201");
  await expect(page.locator("#new-source-2-branch option")).toHaveCount(3);
  await page.locator("#new-source-2-branch").selectOption("main");
  await page
    .getByRole("button", { name: "Create environment", exact: true })
    .click();
  await expect.poll(() => saved).not.toBeNull();
  expect(saved).toEqual({
    name: "Mixed sources",
    database_id: null,
    repositories: [
      { git_connection_id: 10, remote_id: "102", branch: "release" },
      { git_connection_id: 30, remote_id: "301", branch: "main" },
      { git_connection_id: 20, remote_id: "201", branch: "main" },
    ],
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("named AI configs share quota windows and targeted authentication never changes another identity", async ({
  page,
}) => {
  await base(page);
  const attempt = {
    id: "99999999-9999-4999-8999-999999999999",
    provider: "codex",
    status: "AWAITING_USER",
    message: "Complete sign-in on the website for ChatGPT.",
    verification_uri: "https://auth.openai.com/codex/device",
    user_code: "TEST-CODE",
    input_required: false,
  };
  let target = "";
  await page.route("**/api/ai-connections/*/auth/start", (r) => {
    target = r.request().url();
    return r.fulfill({ json: attempt });
  });
  await page.route(`**/api/connections/attempts/${attempt.id}**`, (r) =>
    r.fulfill({ json: attempt }),
  );
  await page.goto("/admin");
  const card = page
    .getByRole("heading", { name: "AI connections", exact: true })
    .locator("..");
  await expect(card.getByText("Session quota:", { exact: false })).toHaveCount(
    2,
  );
  await expect(card.getByText("Weekly quota:", { exact: false })).toHaveCount(
    2,
  );
  await expect(
    card.getByText("Session quota: Unknown", { exact: true }),
  ).toHaveCount(2);
  await expect(
    card.getByText("Weekly quota: Quota exhausted", { exact: true }),
  ).toHaveCount(1);
  await expect(
    card.getByText(
      "These configurations share one authentication identity and the same quota.",
    ),
  ).toBeVisible();
  await page
    .getByRole("region", { name: "Careful review", exact: true })
    .getByRole("button", { name: "Connect with ChatGPT", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Sign in with ChatGPT" }),
  ).toContainText("Careful review");
  expect(target).toContain("/ai-connections/12/auth/start");
  await page
    .getByRole("dialog", { name: "Sign in with ChatGPT" })
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(page.getByRole("dialog", { name: "Sign in with ChatGPT" })).not.toBeVisible();
  let body: Record<string, unknown> | null = null;
  await page.route("**/api/ai-connections", (r) => {
    if (r.request().method() === "POST") body = r.request().postDataJSON();
    return r.fulfill({ json: ai });
  });
  await page
    .getByLabel("Connection name", { exact: true })
    .last()
    .fill("Second review");
  await expect(page.locator("#ai-config-name")).toHaveValue("Second review");
  await page
    .getByLabel("Authentication identity", { exact: true })
    .selectOption("11");
  await expect(page.locator("#ai-config-name")).toHaveValue("Second review");
  await page.getByLabel("Model", { exact: true }).fill("gpt-review");
  await page.getByLabel("Default connection when available").check();
  await expect(page.locator("#ai-config-name")).toHaveValue("Second review");
  await page
    .getByRole("button", { name: "Add AI connection", exact: true })
    .click();
  await expect.poll(() => body).not.toBeNull();
  expect(body).toMatchObject({
    name: "Second review",
    share_identity_from: 11,
    model: "gpt-review",
    is_default: true,
  });
});

test("referenced Git deletion requires an explicit decision and exact connection name", async ({
  page,
}) => {
  await base(page);
  let deletes = 0;
  await page.route("**/api/git-connections/30?**", (r) => {
    deletes++;
    expect(new URL(r.request().url()).searchParams.get("confirm_name")).toBe(
      "GitLab internal",
    );
    return r.fulfill({ json: { status: "DISABLED" } });
  });
  await page.goto("/admin");
  await page
    .getByRole("region", { name: "GitLab internal", exact: true })
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Delete Git connection",
    exact: true,
  });
  await expect(dialog).toContainText(
    "preserves all requests, tickets and historical references",
  );
  await expect(
    dialog.getByRole("button", { name: "Confirm deletion" }),
  ).toBeDisabled();
  await dialog
    .getByLabel("Type the connection name to confirm")
    .fill("GitLab internal");
  await dialog.getByRole("button", { name: "Confirm deletion" }).click();
  await expect(dialog).not.toBeVisible();
  expect(deletes).toBe(1);
});

test("queue names actual model assignments and labels an unassigned request explicitly", async ({
  page,
}) => {
  await base(page);
  await page.route("**/api/queue", (r) =>
    r.fulfill({
      json: [
        {
          id: 1,
          kind: "ANALYZE",
          status: "RUNNING",
          title: "Active analysis",
          assignments: [
            {
              connection_id: 12,
              connection_name: "Careful review",
              agent: "codex",
              model: "gpt-review",
            },
          ],
          started_at: new Date().toISOString(),
          href: "/",
        },
        {
          id: 2,
          kind: "ANALYZE",
          status: "QUEUED",
          title: "Next analysis",
          assignments: [],
          queue_position: 1,
          href: "/",
        },
      ],
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
    queue.getByText("Careful review · gpt-review", { exact: true }),
  ).toBeVisible();
  await expect(queue.getByText("AI not assigned", { exact: true })).toHaveCount(
    1,
  );
  await expect(
    queue.getByText("Queue position: 1", { exact: true }),
  ).toBeVisible();
});

test("analysis audit preserves historical connection and model after a configuration changes", async ({
  page,
}) => {
  await base(page);
  const id = "44444444-4444-4444-8444-444444444444";
  await page.route(`**/api/requests/${id}`, (r) =>
    r.fulfill({
      json: {
        id,
        need: "Review an export",
        status: "ERROR",
        language: "en",
        confrontation: false,
        environment_name: "Mixed sources",
        baseline: [
          {
            repository: "git-source/42",
            path: "team/fork",
            connection_name: "Historical GitLab",
            branch: "release",
            sha: "a".repeat(40),
            is_fork: true,
            parent: { path: "upstream/app" },
          },
        ],
        database: {},
        questions: [],
        conversation: [],
        understanding: "Export review",
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
            steps: [
              {
                connection_name: "Historical assistant",
                provider: "codex",
                model: "old-model",
                status: "ERROR",
                failure: "MODEL_UNAVAILABLE",
                diagnostic:
                  "The selected model is unavailable for this AI connection. Choose an accepted model in Settings and retry.",
              },
              {
                connection_name: "Backup at execution",
                provider: "claude",
                model: "backup-model",
                status: "DONE",
              },
            ],
          },
        ],
      },
    }),
  );
  await page.goto(`/requests/${id}`);
  await page.getByText("Analysis assignment history", { exact: true }).click();
  await expect(
    page.getByText(
      "Step 1 · Historical assistant · codex · old-model · Interrupted",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Step 2 · Backup at execution · claude · backup-model · Completed",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByText(
      "The selected model is unavailable for this AI connection. Choose an accepted model in Settings and retry.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByText("Analysis reference", { exact: true }).click();
  await expect(
    page.getByText("team/fork · release", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Historical GitLab", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("a".repeat(40), { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
