import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const timestamp = "2026-10-22T12:00:00Z";
const records = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    title: "Add an approval reminder",
    external_id: "14",
    external_key: "TEAM-14",
    url: "https://tickets.example.test/TEAM-14",
    platform: "jira",
    project: "TEAM",
    environment_name: "Production",
    request_id: "request-one",
    version_number: 2,
    status: "PUBLISHED",
    error: "",
    created_at: timestamp,
    updated_at: timestamp,
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    title: "Clarify contract validation",
    external_id: "",
    external_key: "",
    url: "",
    platform: "github",
    project: "team/app",
    environment_name: "Staging",
    request_id: "request-two",
    version_number: 1,
    status: "UNCERTAIN",
    error:
      "Publication status is uncertain. Check the destination before retrying.",
    created_at: timestamp,
    updated_at: timestamp,
  },
];
const details = records.map((record, index) => ({
  ...record,
  description: `## Submitted content v${record.version_number}\n\n${index ? "Validation rules require checking." : "Send an approval reminder after three days."}`,
  labels: index ? [] : ["business", "approval"],
  payload_available: true,
}));
async function base(page: Page, language = "en") {
  await page.route("**/api/settings", (route) =>
    route.fulfill({
      json: { name: "SpecHelper", primary_color: "#2563eb", language },
    }),
  );
  await page.route("**/api/queue", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/environments", (route) =>
    route.fulfill({
      json: [
        { id: 1, name: "Production" },
        { id: 2, name: "Staging" },
      ],
    }),
  );
  await page.route("**/api/tickets?*", (route) =>
    route.fulfill({
      json: {
        items: records,
        total: records.length,
        page: 1,
        page_size: 20,
        environments: ["Production", "Staging"],
        statuses: ["PUBLISHING", "PUBLISHED", "ERROR", "UNCERTAIN"],
      },
    }),
  );
  for (const detail of details)
    await page.route(`**/api/tickets/${detail.id}`, (route) =>
      route.fulfill({ json: detail }),
    );
}

test("ticket selection displays submitted content, labels, immutable provenance and honest synchronization metadata", async ({
  page,
}) => {
  await base(page);
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/tickets") && request.method() !== "GET")
      writes.push(request.method());
  });
  await page.goto("/tickets");
  const table = page.getByRole("region", { name: "Ticket table", exact: true });
  await expect(
    table.getByRole("button", { name: records[0].title, exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const selected = page.getByRole("region", {
    name: "Selected ticket",
    exact: true,
  });
  await expect(selected.getByTestId("ticket-description")).toContainText(
    "Send an approval reminder after three days.",
  );
  await expect(selected.getByText("business", { exact: true })).toBeVisible();
  await expect(
    selected.getByRole("link", {
      name: "Published analysis · v2",
      exact: true,
    }),
  ).toHaveAttribute("href", "/requests/request-one?version=2");
  await expect(
    selected.getByText(/not a live external ticket status/),
  ).toBeVisible();
  await table
    .getByRole("button", { name: records[1].title, exact: true })
    .click();
  await expect(selected.getByTestId("ticket-description")).toContainText(
    "Validation rules require checking.",
  );
  await expect(
    selected.getByRole("link", {
      name: "Published analysis · v1",
      exact: true,
    }),
  ).toHaveAttribute("href", "/requests/request-two?version=1");
  await expect(selected.getByRole("alert")).toContainText(
    "Publication status is uncertain",
  );
  await expect(
    selected.getByRole("link", { name: "Open ticket", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Refresh records", exact: true })
    .click();
  await expect(selected.getByTestId("ticket-description")).toBeVisible();
  await expect(page.getByText("Loading tickets…", { exact: true })).toHaveCount(
    0,
  );
  expect(writes).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `../.local/screenshots/v18-tickets-${test.info().project.name}.png`,
    fullPage: true,
  });
});

test("ticket filters are server-backed and empty matches have a useful next action", async ({
  page,
}) => {
  await base(page);
  const query: string[] = [];
  await page.route("**/api/tickets?*", (route) => {
    const url = new URL(route.request().url());
    query.push(url.search);
    return route.fulfill({
      json: {
        items: url.searchParams.get("status") === "ERROR" ? [] : records,
        total: url.searchParams.get("status") === "ERROR" ? 0 : 2,
        page: 1,
        page_size: 20,
        statuses: ["PUBLISHED", "ERROR", "UNCERTAIN"],
      },
    });
  });
  await page.goto("/tickets");
  await expect(
    page.getByLabel("Publication status", { exact: true }),
  ).toHaveValue("all");
  await page.getByLabel("Search tickets", { exact: true }).fill("validation");
  await page.getByLabel("Platform", { exact: true }).selectOption("github");
  await page.getByLabel("Environment", { exact: true }).selectOption("Staging");
  await page
    .getByLabel("Publication status", { exact: true })
    .selectOption("ERROR");
  await expect(
    page.getByText("No ticket publications match these filters.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "View requests", exact: true }),
  ).toHaveAttribute("href", "/");
  const last = new URLSearchParams(query.at(-1));
  expect(Object.fromEntries(last)).toEqual({
    platform: "github",
    environment: "Staging",
    status: "ERROR",
    search: "validation",
    page: "1",
  });
  await expect(
    page.getByRole("region", { name: "Selected ticket", exact: true }),
  ).toHaveCount(0);
});

test("selected detail failure and partial metadata remain truthful and can be retried", async ({
  page,
}) => {
  await base(page);
  let failure = true;
  await page.route(`**/api/tickets/${records[0].id}`, (route) =>
    failure
      ? route.fulfill({
          status: 503,
          json: { detail: "Temporary ticket storage failure" },
        })
      : route.fulfill({
          json: {
            ...details[0],
            description: "",
            labels: [],
            payload_available: false,
          },
        }),
  );
  await page.goto("/tickets");
  const selected = page.getByRole("region", {
    name: "Selected ticket",
    exact: true,
  });
  await expect(selected.getByRole("alert")).toContainText(
    "Temporary ticket storage failure",
  );
  await expect(selected.getByTestId("ticket-description")).toHaveCount(0);
  failure = false;
  await page
    .getByRole("button", { name: "Refresh records", exact: true })
    .click();
  await expect(selected.getByRole("status")).toContainText(
    "The submitted content is unavailable",
  );
  await expect(
    selected.getByText("No labels were submitted.", { exact: true }),
  ).toBeVisible();
  await expect(
    selected.getByRole("link", {
      name: "Published analysis · v2",
      exact: true,
    }),
  ).toBeVisible();
});

test("ticket list loading keeps filters usable and errors offer a retry", async ({
  page,
}) => {
  await base(page);
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/tickets?*", async (route) => {
    await pending;
    await route.fulfill({
      status: 503,
      json: { detail: "Temporary ticket storage failure" },
    });
  });
  await page.goto("/tickets");
  await expect(
    page.getByText("Loading tickets…", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Search tickets", { exact: true }),
  ).toBeVisible();
  release();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Temporary ticket storage failure" }),
  ).toContainText("Refresh to try again.");
  await expect(
    page.getByRole("button", { name: "Refresh records", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByText("No ticket publications match these filters.", {
      exact: true,
    }),
  ).toHaveCount(0);
});

test("French ticket filters, detail and publication metadata are translated", async ({
  page,
}) => {
  await base(page, "fr");
  await page.goto("/tickets");
  await expect(
    page.getByLabel("État de publication", { exact: true }),
  ).toBeVisible();
  const selected = page.getByRole("region", {
    name: "Ticket sélectionné",
    exact: true,
  });
  await expect(
    selected.getByRole("heading", { name: "Étiquettes / tags", exact: true }),
  ).toBeVisible();
  await expect(
    selected.getByRole("heading", {
      name: "Publication et synchronisation",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Actualiser les enregistrements",
      exact: true,
    }),
  ).toBeVisible();
});
