import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import { translate } from "../src/lib/i18n";

const id = "45454545-4545-4545-8545-454545454545";
const stamp = "2026-10-30T12:00:00Z";
function accounts() {
  return Array.from({ length: 6 }, (_, index) => ({
    id: index + 1, name: `Account ${index + 1}`, platform: "jira", enabled: index !== 4,
    status: index === 5 ? "UNAVAILABLE" : "CONNECTED", environment_ids: [1],
    base_url: "https://jira.example.test", username: `account-${index + 1}@example.test`,
    api_version: "v1", has_secret: true, has_app_token: false, error: "", projects: [], default_project: "",
  }));
}
async function setup(page: Page, language: "en" | "fr") {
  let connections = accounts();
  let environment: any = { id: 1, name: "Staging", status: "READY", revision: 1,
    repositories: [{ id: 1, repository: "fixture/project", branch: "main", sha: "a".repeat(40) }],
    publication_connection_ids: [], publication_connections: [] };
  const changes: any[] = [];
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#168e95" } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [], github: { status: "CONNECTED" } } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4" } }));
  await page.route("**/api/environments", route => route.fulfill({ json: [environment] }));
  await page.route("**/api/environments/1", route => {
    const payload = route.request().postDataJSON(); changes.push(payload);
    environment = { ...environment, ...payload, revision: environment.revision + 1,
      repositories: payload.repositories.map((item: any) => ({ ...environment.repositories.find((previous: any) => previous.repository === item.repository), ...item })),
      publication_connections: connections.filter(item => payload.publication_connection_ids.includes(item.id)) };
    return route.fulfill({ json: environment });
  });
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, route => {
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON(); changes.push(payload);
      connections = [...connections, { ...payload, id: 7, has_secret: true, environment_ids: [], status: "UNKNOWN" }];
      return route.fulfill({ json: connections.at(-1) });
    }
    return route.fulfill({ json: connections });
  });
  await page.route("**/api/ticket-connectors/1", route => {
    const payload = route.request().postDataJSON(); changes.push(payload);
    connections = connections.map(item => item.id === 1 ? { ...item, ...payload } : item);
    return route.fulfill({ json: connections[0] });
  });
  return { changes };
}

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(key, language);

  test(`global publication catalogue supports free names without environment ownership in ${language}`, async ({ page }) => {
    const { changes } = await setup(page, language);
    await page.goto("/admin?tab=connectors");
    await expect(page.getByRole("navigation", { name: t("Administration"), exact: true }).getByRole("button", { name: t("Ticket publication"), exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Account 1", exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Edit {name}").replace("{name}", "Account 1"), exact: true }).click();
    await page.getByLabel(t("Connection name"), { exact: true }).fill("Any / internal reference");
    await expect(page.getByLabel(t("Secret / API token"), { exact: true })).toHaveValue("");
    await page.getByRole("button", { name: t("Save connector"), exact: true }).click();
    await expect(page.getByRole("heading", { name: "Any / internal reference", exact: true })).toBeVisible();
    expect(changes[0]).not.toHaveProperty("environment_id");
    expect(changes[0]).not.toHaveProperty("secret");
    await page.getByRole("button", { name: t("New connector"), exact: true }).click();
    await page.getByLabel(t("Connection name"), { exact: true }).fill("Independent designation");
    await page.getByLabel(t("Platform"), { exact: true }).selectOption("jira");
    await page.locator("#publication-connection-url").fill("https://jira.example.test");
    await page.getByLabel(t("Secret / API token"), { exact: true }).fill("synthetic-ui-only-token");
    await page.getByRole("button", { name: t("Save connector"), exact: true }).click();
    await expect(page.getByRole("heading", { name: "Independent designation", exact: true })).toBeVisible();
    expect(changes[1]).not.toHaveProperty("environment_id");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`four accounts can be associated and removed in the environment editor in ${language}`, async ({ page }) => {
    const { changes } = await setup(page, language);
    await page.goto("/admin?tab=environments");
    const card = page.locator(".environment-card");
    await card.getByRole("button", { name: t("Edit {name}").replace("{name}", "Staging"), exact: true }).click();
    const dialog = page.getByRole("dialog");
    for (const number of [1, 2, 3, 4]) await dialog.getByRole("checkbox", { name: new RegExp(`Account ${number}`) }).check();
    await dialog.getByRole("button", { name: t("Review changes"), exact: true }).click();
    await dialog.getByRole("button", { name: t("Confirm changes"), exact: true }).click();
    await expect.poll(() => changes[0]?.publication_connection_ids).toEqual([1, 2, 3, 4]);
    const summary = card.getByRole("region", { name: t("Publication destinations"), exact: true });
    await expect(summary.getByRole("listitem")).toHaveCount(4);
    await card.getByRole("button", { name: t("Edit {name}").replace("{name}", "Staging"), exact: true }).click();
    await dialog.getByRole("checkbox", { name: /Account 2/ }).uncheck();
    await dialog.getByRole("button", { name: t("Review changes"), exact: true }).click();
    await dialog.getByRole("button", { name: t("Confirm changes"), exact: true }).click();
    await expect.poll(() => changes[1]?.publication_connection_ids).toEqual([1, 3, 4]);
    await expect(summary.getByRole("listitem")).toHaveCount(3);
  });

  test(`publication explicitly selects an account and destination in ${language}`, async ({ page }) => {
    await setup(page, language);
    const endpoint = `/api/requests/${id}/versions/1`;
    const version = { id: "version-1", number: 1, status: "READY", created_at: stamp, ticket: { title: "Verified change" }, markdown: "# Verified change", evidence: { blocking: false, claims: [], limitations: [], database: { status: "not_configured", limitations: [], checks: [] } } };
    const detail = { id, title: "Verified change", need: "Explain the change", workflow: "request", analysis_protocol: "2.4", status: "READY", language,
      environment_id: 1, environment_name: "Staging", created_at: stamp, baseline: [], database: {}, questions: [], conversation: [], progress: [], attachments: [], error: "", messages: [],
      versions: [{ number: 1, status: "READY", created_at: stamp }], latest_version: version };
    await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: detail }));
    let submitted: any;
    const selectedAccounts: string[] = [];
    await page.route(`**${endpoint}/publications`, route => {
      if (route.request().method() === "GET") return route.fulfill({ json: [] });
      submitted = route.request().postDataJSON();
      return route.fulfill({ json: { id: "publication-1", status: "PUBLISHED", url: "https://jira.example.test/browse/TEAM-1", attachment_delivery: [] } });
    });
    await page.route(/\/api\/ticket-connectors\/\d+\/projects$/, route => {
      selectedAccounts.push(new URL(route.request().url()).pathname.split("/")[3]);
      return route.fulfill({ json: [{ id: "TEAM", name: "Accessible project" }, { id: "OTHER", name: "Another accessible project" }] });
    });
    await page.route(`**${endpoint}/publication-draft?*`, route => route.fulfill({ json: {
      draft_id: "draft-1", draft_revision: 1, title: "Verified change", body: "Short verified description", ticket_format: "standard",
      template_id: "", issue_type: "", fields: [], values: {}, labels: [], assignees: [], templates: [], issue_types: [], defaults: {},
      revision: "metadata-4", format: "markdown", publication_allowed: true, publication_blockers: [], available_attachments: [], selected_attachments: [],
    } }));
    await page.goto(`/requests/${id}`);
    await page.getByRole("button", { name: t("Prepare ticket"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Publish ticket"), exact: true });
    const account = dialog.getByLabel(t("Publication connection"), { exact: true });
    await expect(account).toHaveValue("");
    await expect(account.locator('option[value="5"]')).toBeDisabled();
    await expect(account.locator('option[value="6"]')).toBeDisabled();
    expect(selectedAccounts).toEqual([]);
    await account.selectOption("4");
    const project = dialog.getByLabel(t("Project / repository"), { exact: true });
    await expect(project.locator('option[value="OTHER"]')).toHaveText("Another accessible project");
    await expect(project).toHaveValue("");
    await project.selectOption("OTHER");
    await expect(dialog.getByLabel(t("Ticket description"), { exact: true })).toHaveValue("Short verified description");
    expect(submitted).toBeUndefined();
    await dialog.getByRole("button", { name: t("Create ticket"), exact: true }).click();
    await expect.poll(() => submitted).toMatchObject({ connector_id: 4, project: "OTHER", confirmed: true });
    expect(selectedAccounts).toEqual(["4"]);
  });
}
