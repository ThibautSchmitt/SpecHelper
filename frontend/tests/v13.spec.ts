import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const id = "88888888-8888-4888-8888-888888888888";
const connector = {
  environment_id: 1,
  id: 1,
  name: "Team GitHub",
  platform: "github",
  base_url: "",
  username: "",
  api_version: "",
  has_secret: false,
  has_app_token: false,
  status: "CONNECTED",
  error: "",
  projects: ["team/app"],
  default_project: "team/app",
};
const version = {
  id: "v1",
  number: 1,
  language: "en",
  format_version: "1.2",
  status: "READY",
  created_at: "2026-10-22T08:00:00Z",
  ticket: {
    title: "Approved export",
    context: "Business context",
    need: "Export active records",
    expected_behavior: "Only active records",
    proposed_solution: "Filter the export",
    technical_impact: ["Export service"],
    risks: [],
    acceptance_criteria: ["Inactive records excluded"],
  },
  markdown: "# Approved export",
  goal_markdown: "# Goal",
  artifacts: { "goal.md": "/goal-v1.md", "ticket.md": "/ticket-v1.md" },
};
const detail = {
  id,
  language: "en",
  need: "Export only active records",
  confrontation: false,
  status: "READY",
  environment_id: 1,
  environment_name: "Production",
  created_at: "2026-10-22T08:00:00Z",
  baseline: [],
  database: {},
  questions: [],
  conversation: [],
  understanding: "Active exports",
  progress: [],
  error: "",
  attachments: [],
  ticket: version.ticket,
  markdown: version.markdown,
  latest_version: {
    ...version,
    number: 2,
    ticket: { ...version.ticket, title: "Newest export" },
  },
  versions: [
    { number: 2, status: "READY", created_at: version.created_at },
    { number: 1, status: "READY", created_at: version.created_at },
  ],
  messages: [],
};
const publicationOptions = new RegExp(`/api/requests/${id}/versions/1/publication-(?:preview|draft)(?:\\?.*)?$`);
const options = {
  title: "Approved export",
  body: "## Context\n\nActive records.\n\n- Reviewed requirement\n\n[Unsafe](javascript:alert(1))",
  fields: [
    {
      id: "business_owner",
      label: "Business owner",
      type: "text",
      required: true,
      options: [],
      default: "",
      description: "A human must identify the owner.",
    },
    {
      id: "consent",
      label: "Reviewed constraints",
      type: "checkbox",
      required: true,
      options: [],
      default: false,
    },
  ],
  labels: [{ id: "enhancement", name: "Enhancement" }],
  assignees: [{ id: "alex", name: "Alex" }],
  templates: [{ id: "change.md", name: "Change request" }],
  issue_types: [],
  revision: "revision-1",
  format: "markdown",
  values: {},
  defaults: { labels: ["enhancement"] },
};

async function base(page: Page) {
  await page.route("**/api/ai-connections", (r) =>
    r.fulfill({
      json: [
        {
          id: 1,
          name: "ChatGPT",
          agent: "codex",
          enabled: true,
          status: "CONNECTED",
          availability: "AVAILABLE",
          quota_windows: {},
        },
      ],
    }),
  );
  await page.route("**/api/connections", (r) =>
    r.fulfill({
      json: {
        github: { status: "CONNECTED", account: "team" },
        ais: [
          {
            id: 1,
            agent: "codex",
            status: "CONNECTED",
            availability: "AVAILABLE",
            enabled: true,
          },
        ],
        databases: [],
      },
    }),
  );
  await page.route("**/api/environments", (r) =>
    r.fulfill({
      json: [{ id: 1, name: "Production", status: "READY", repositories: [] }],
    }),
  );
  await page.route("**/api/requests", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/queue", (r) => r.fulfill({ json: [] }));
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, (r) =>
    r.fulfill({ json: [connector] }),
  );
  await page.route("**/api/ticket-connectors/1/projects", (r) =>
    r.fulfill({
      json: [
        { id: "team/app", name: "Application" },
        { id: "private/forbidden", name: "Forbidden project" },
      ],
    }),
  );
  await page.route(`**/api/requests/${id}`, (r) => r.fulfill({ json: detail }));
  await page.route(`**/api/requests/${id}/versions/1`, (r) =>
    r.fulfill({ json: version }),
  );
  await page.route(`**/api/requests/${id}/versions/1/publications`, (r) =>
    r.fulfill({ json: [] }),
  );
  await page.route(
    publicationOptions,
    (r) => r.fulfill({ json: options }),
  );
  await page.route("**/api/tickets?**", (r) =>
    r.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } }),
  );
}
async function queue(page: Page) {
  if (
    await page
      .getByRole("button", { name: "Task queue", exact: true })
      .isVisible()
  ) {
    await page.getByRole("button", { name: "Task queue", exact: true }).click();
    return page.getByRole("dialog", { name: "Task queue", exact: true });
  }
  return page.getByRole("complementary", { name: "Task queue", exact: true });
}

test("persistent navigation and real shared queue remain available across pages", async ({
  page,
}) => {
  await base(page);
  let running = true;
  await page.route("**/api/queue", (r) =>
    r.fulfill({
      json: [
        {
          id: 1,
          kind: "ANALYZE",
          status: running ? "RUNNING" : "DONE",
          title: "Shared export request",
          environment_name: "Production",
          operation: "Analyze request",
          agent: "codex",
          request_status: running ? "ANALYZING" : "NEEDS_CLARIFICATION",
          queue_position: null,
          started_at: new Date(Date.now() - 65000).toISOString(),
          finished_at: running ? null : new Date().toISOString(),
          error: "",
          href: `/requests/${id}`,
        },
        {
          id: 2,
          kind: "ANALYZE",
          status: "QUEUED",
          title: "Next FIFO request",
          environment_name: "Production",
          operation: "Analyze request",
          agent: "",
          request_status: "QUEUED",
          queue_position: 1,
          started_at: null,
          finished_at: null,
          error: "",
          href: `/requests/${id}`,
        },
      ],
    }),
  );
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(nav.getByRole("link")).toHaveText([
    "Requests",
    "Questions",
    "Tickets",
  ]);
  await expect(
    page
      .getByRole("complementary", { name: "Instance navigation" })
      .getByText("Available", { exact: true }),
  ).toBeVisible();
  let panel = await queue(page);
  await expect(
    panel.getByText("Shared export request", { exact: true }),
  ).toBeVisible();
  await expect(
    panel.getByText("Queue position: 1", { exact: true }),
  ).toBeVisible();
  await expect(panel.locator('[data-job="1"] .queue-context')).toHaveAttribute("title", /Elapsed: 1m/);
  if (await page.getByRole("dialog").isVisible())
    await panel.getByRole("button", { name: "Close", exact: true }).click();
  await nav.getByRole("link", { name: "Tickets", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Tickets", exact: true }),
  ).toBeVisible();
  running = false;
  panel = await queue(page);
  await expect(panel.getByText("A business answer is needed.")).toBeVisible({
    timeout: 6000,
  });
  await panel.getByRole("link", { name: /Shared export request/ }).click();
  await expect(page).toHaveURL(new RegExp(id));
  await expect(
    page.getByRole("heading", { name: "Newest export" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("publication edits exact version, validates target fields and reconciles uncertain attempts", async ({
  page,
}) => {
  await base(page);
  const sent: Record<string, unknown>[] = [];
  let saved: Record<string, unknown> | null = null;
  await page.route(
    `**/api/requests/${id}/versions/1/publications`,
    async (r) => {
      if (r.request().method() === "GET")
        return r.fulfill({
          json: saved
            ? [
                {
                  id: "pub",
                  status: "UNCERTAIN",
                  connector_id: 1,
                  project: "team/app",
                  idempotency_key: saved.idempotency_key,
                  snapshot: saved,
                },
              ]
            : [],
        });
      const payload = r.request().postDataJSON();
      sent.push(payload);
      saved = payload;
      return r.fulfill({
        json:
          sent.length === 1
            ? { id: "pub", status: "UNCERTAIN" }
            : {
                id: "pub",
                status: "PUBLISHED",
                url: "https://github.com/team/app/issues/42",
                external_id: "42",
              },
      });
    },
  );
  await page.goto(`/requests/${id}?version=1`);
  await expect(
    page.getByRole("heading", { name: "Approved export", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Publish ticket", exact: true })
    .click();
  let modal = page.getByRole("dialog", { name: "Publish ticket", exact: true });
  await expect(modal.getByLabel("Ticket title", { exact: true })).toHaveValue(
    "Approved export",
  );
  await expect(
    modal.getByLabel("Project / repository").getByRole("option"),
  ).toHaveText(["Select a project", "Application"]);
  await expect(modal.getByLabel(/priority/i)).toHaveCount(0);
  await expect(modal.locator(".markdown-preview h2")).toHaveText("Context");
  await expect(modal.locator('a[href^="javascript:"]')).toHaveCount(0);
  await modal
    .getByLabel("Ticket title", { exact: true })
    .fill("Reviewed export title");
  await expect(modal.getByRole("button", { name: "Create ticket", exact: true })).toBeDisabled();
  expect(sent).toHaveLength(0);
  await modal
    .getByLabel("Business owner", { exact: false })
    .fill("Operations team");
  await modal.getByLabel("Reviewed constraints", { exact: false }).check();
  await modal
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await expect(
    modal.getByRole("button", { name: "Verify publication", exact: true }),
  ).toBeVisible();
  expect(sent[0].title).toBe("Reviewed export title");
  expect(sent[0].labels).toEqual(["enhancement"]);
  expect(sent[0].fields).toEqual({
    business_owner: "Operations team",
    consent: true,
  });
  await modal.getByRole("button", { name: "Close", exact: true }).click();
  await page.reload();
  await page.evaluate(() => sessionStorage.clear());
  await page
    .getByRole("button", { name: "Publish ticket", exact: true })
    .click();
  modal = page.getByRole("dialog", { name: "Publish ticket", exact: true });
  await modal
    .getByRole("button", { name: "Verify publication", exact: true })
    .click();
  await expect(
    modal.getByRole("link", { name: "Open ticket", exact: true }),
  ).toHaveAttribute("href", "https://github.com/team/app/issues/42");
  expect(sent[1]).toEqual(sent[0]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("changed templates require a review and tickets link to their immutable result", async ({
  page,
}) => {
  await base(page);
  let previews = 0;
  let posts = 0;
  await page.route(
    publicationOptions,
    (r) => {
      if (r.request().method() !== "PUT") previews++;
      return r.fulfill({
        json: {
          ...options,
          revision: `revision-${previews}`,
          format: "adf",
          fields: [],
        },
      });
    },
  );
  await page.route(`**/api/requests/${id}/versions/1/publications`, (r) => {
    if (r.request().method() === "GET") return r.fulfill({ json: [] });
    posts++;
    return r.fulfill({
      status: 409,
      json: {
        detail:
          "Publication options changed. Review the current fields before creating the ticket.",
      },
    });
  });
  await page.goto(`/requests/${id}?version=1`);
  await page
    .getByRole("button", { name: "Publish ticket", exact: true })
    .click();
  const modal = page.getByRole("dialog", {
    name: "Publish ticket",
    exact: true,
  });
  await expect(modal.getByLabel("Ticket title")).toHaveValue("Approved export");
  await expect(modal.locator(".markdown-preview h2")).toHaveCount(0);
  await expect(modal.locator(".markdown-preview")).toContainText("## Context");
  await modal
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await expect(modal.getByRole("alert")).toContainText(
    "Publication options changed",
  );
  await expect(
    modal.getByRole("button", { name: "Create ticket", exact: true }),
  ).toHaveCount(0);
  await modal
    .getByRole("button", { name: "Reload and review options", exact: true })
    .click();
  await expect(
    modal.getByRole("button", { name: "Create ticket", exact: true }),
  ).toBeVisible();
  expect(posts).toBe(1);
  expect(previews).toBe(2);
  await modal.getByRole("button", { name: "Close", exact: true }).click();
  await page.route("**/api/tickets/ticket", (route) =>
    route.fulfill({
      json: {
        id: "ticket",
        title: "Reviewed export title",
        external_id: "42",
        external_key: "42",
        url: "https://github.com/team/app/issues/42",
        platform: "github",
        project: "team/app",
        environment_name: "Production",
        request_id: id,
        version_number: 1,
        status: "PUBLISHED",
        created_at: version.created_at,
        updated_at: version.created_at,
        error: "",
        description: "Reviewed export content",
        labels: [],
        payload_available: true,
      },
    }),
  );
  const queries: string[] = [];
  await page.route("**/api/tickets?**", (r) => {
    queries.push(r.request().url());
    return r.fulfill({
      json: {
        items: [
          {
            id: "ticket",
            title: "Reviewed export title",
            external_id: "42",
            url: "https://github.com/team/app/issues/42",
            platform: "github",
            project: "team/app",
            environment_name: "Production",
            request_id: id,
            version_number: 1,
            status: "PUBLISHED",
            created_at: version.created_at,
            error: "",
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      },
    });
  });
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Tickets", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Published analysis · v1", exact: true }),
  ).toHaveAttribute("href", `/requests/${id}?version=1`);
  await page.getByLabel("Platform", { exact: true }).selectOption("github");
  await page.getByLabel("Search tickets").fill("export");
  await expect.poll(() => queries.at(-1)).toContain("search=export");
  await page
    .getByRole("link", { name: "Published analysis · v1", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Approved export", exact: true }),
  ).toBeVisible();
});

test("connector settings keep saved secrets private and expose explicit GLPI compatibility", async ({
  page,
}) => {
  await base(page);
  await page.route("**/api/system", (r) => r.fulfill({ json: { jobs: [] } }));
  const jira = {
    ...connector,
    id: 2,
    name: "Team Jira",
    platform: "jira",
    base_url: "https://jira.example",
    username: "owner@example.test",
    has_secret: true,
    projects: ["TEAM"],
    default_project: "TEAM",
  };
  let payload: Record<string, unknown> | null = null;
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, (r) =>
    r.fulfill({ json: [jira] }),
  );
  await page.route("**/api/ticket-connectors/2", (r) => {
    payload = r.request().postDataJSON();
    return r.fulfill({ json: jira });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  await page.getByRole("button", { name: /Team Jira/ }).click();
  await expect(
    page.getByLabel("Secret / API token", { exact: true }),
  ).toHaveValue("");
  await page
    .getByRole("button", { name: "Save connector", exact: true })
    .click();
  await expect.poll(() => payload).not.toBeNull();
  expect(payload).toMatchObject({ environment_id: 1 });
  expect(payload).not.toHaveProperty("secret");
  expect(payload).not.toHaveProperty("app_token");
  await page
    .getByRole("button", { name: "New connector", exact: true })
    .click();
  await page.getByLabel("Platform", { exact: true }).selectOption("glpi");
  await expect(page.getByLabel("API compatibility")).toHaveValue("v1");
  await expect(
    page.getByText(
      "Only GLPI REST API v1 is supported. API v2 is not compatible.",
    ),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("issue form preview renders live target fields once and permits a field-only body", async ({
  page,
}) => {
  await base(page);
  await page.route(
    publicationOptions,
    (route) =>
      route.fulfill({ json: { ...options, body: "", render_fields: true } }),
  );
  let sent: Record<string, unknown> | null = null;
  await page.route(`**/api/requests/${id}/versions/1/publications`, (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    sent = route.request().postDataJSON();
    return route.fulfill({
      json: {
        id: "pub",
        status: "PUBLISHED",
        external_id: "43",
        url: "https://github.com/team/app/issues/43",
      },
    });
  });
  await page.goto(`/requests/${id}?version=1`);
  await page
    .getByRole("button", { name: "Publish ticket", exact: true })
    .click();
  const modal = page.getByRole("dialog", {
    name: "Publish ticket",
    exact: true,
  });
  await expect(
    modal.getByLabel("Ticket description", { exact: true }),
  ).toHaveValue("");
  await modal
    .getByLabel("Business owner", { exact: false })
    .fill("Support team");
  await modal.getByLabel("Reviewed constraints", { exact: false }).check();
  await expect(modal.locator(".markdown-preview h3")).toHaveText([
    "Business owner",
    "Reviewed constraints",
  ]);
  await expect(modal.locator(".markdown-preview")).toContainText(
    "Support team",
  );
  await expect(modal.locator(".markdown-preview")).toContainText("[x]");
  await modal
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await expect(
    modal.getByRole("link", { name: "Open ticket", exact: true }),
  ).toBeVisible();
  expect(sent).toMatchObject({
    body: "",
    fields: { business_owner: "Support team", consent: true },
  });
});

test("publication is blocked until existing attempts can be checked", async ({
  page,
}) => {
  await base(page);
  let checked = false;
  let posts = 0;
  await page.route(`**/api/requests/${id}/versions/1/publications`, (route) => {
    if (route.request().method() === "POST") {
      posts++;
      return route.fulfill({ json: { status: "PUBLISHED" } });
    }
    return checked
      ? route.fulfill({ json: [] })
      : route.fulfill({ status: 503, json: { detail: "Service unavailable" } });
  });
  await page.goto(`/requests/${id}?version=1`);
  await page
    .getByRole("button", { name: "Publish ticket", exact: true })
    .click();
  const modal = page.getByRole("dialog", {
    name: "Publish ticket",
    exact: true,
  });
  await expect(
    modal.getByText(
      "Previous publications could not be checked. Check again before creating a ticket.",
    ),
  ).toBeVisible();
  await expect(
    modal.getByRole("button", { name: "Create ticket", exact: true }),
  ).toHaveCount(0);
  checked = true;
  await modal
    .getByRole("button", { name: "Check publications again", exact: true })
    .click();
  await expect(
    modal.getByRole("button", { name: "Create ticket", exact: true }),
  ).toBeVisible();
  expect(posts).toBe(0);
});

test("another browser's successful publication resolves a conflicting edited submission", async ({
  page,
}) => {
  await base(page);
  let published = false;
  let posts = 0;
  await page.route(
    publicationOptions,
    (r) => r.fulfill({ json: { ...options, fields: [] } }),
  );
  await page.route(`**/api/requests/${id}/versions/1/publications`, (r) => {
    if (r.request().method() === "GET")
      return r.fulfill({
        json: published
          ? [
              {
                id: "other-browser",
                status: "PUBLISHED",
                connector_id: 1,
                project: "team/app",
                idempotency_key: "another-key",
                url: "https://github.com/team/app/issues/44",
                external_id: "44",
                snapshot: {},
              },
            ]
          : [],
      });
    posts++;
    published = true;
    return r.fulfill({
      status: 409,
      json: {
        detail:
          "This result already has a publication attempt for this destination. Review that attempt first.",
      },
    });
  });
  await page.goto(`/requests/${id}?version=1`);
  await page
    .getByRole("button", { name: "Publish ticket", exact: true })
    .click();
  const modal = page.getByRole("dialog", {
    name: "Publish ticket",
    exact: true,
  });
  await expect(modal.getByLabel("Ticket title")).toHaveValue("Approved export");
  await modal.getByLabel("Ticket title").fill("A different reviewed title");
  await modal
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await expect(
    modal.getByRole("link", { name: "Open ticket", exact: true }),
  ).toHaveAttribute("href", "https://github.com/team/app/issues/44");
  expect(posts).toBe(1);
  await expect(
    modal.getByRole("button", { name: "Verify publication", exact: true }),
  ).toHaveCount(0);
});
