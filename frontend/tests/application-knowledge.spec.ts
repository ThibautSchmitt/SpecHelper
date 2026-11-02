import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";
import type { Page } from "@playwright/test";

async function setup(page: Page, language: "en" | "fr", theme = "light") {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { authenticated: true, mode: "local" } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [] } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4" } }));
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), theme);
}

function configuration() {
  return { instructions: "Declared business vocabulary", official_references: [{ url: "https://example.org/guide", note: "Applicable to active claims" }], revision: 1, max_files: 20, max_file_size: 26214400, resources: [{
    id: "policy", name: "policy.md", filename: "policy.md", enabled: true, content_type: "text/markdown", size: 27,
    sha256: "a".repeat(64), version: 1, version_id: "version-1", updated_at: "2026-11-02T04:00:00Z", preview: "Declared policy <script>window.injected=true</script>", agent_readable: true,
  }] };
}

for (const language of ["en", "fr"] as const) for (const theme of ["light", "dark"]) {
  const t = (key: string) => translate(key, language);
  test(`compact knowledge preserves unsaved text and links through document changes in ${language} ${theme}`, async ({ page }) => {
    await setup(page, language, theme);
    let current = configuration(), reads = 0;
    const methods: string[] = [];
    await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Fixture application", status: "READY", repositories: [], revision: 1, knowledge_summary: { has_text: true, documents: 1, sites: 1 } }] }));
    await page.route("**/api/environments/1/context**", route => {
      const request = route.request();
      if (request.method() === "GET") reads++;
      else {
        methods.push(request.method());
        if (request.method() === "PUT") {
          expect(request.postDataJSON().expected_revision).toBe(current.revision);
          current = { ...current, ...request.postDataJSON(), revision: current.revision + 1 };
        } else {
          expect(request.postDataBuffer()?.toString()).toContain('name="expected_revision"');
          // Upload replies contain persisted text, not the unsaved browser draft.
          current = { ...current, revision: current.revision + 1, resources: [...current.resources, { ...current.resources[0], id: "procedure", name: "procedure.md", filename: "procedure.md", version_id: "version-2" }] };
        }
      }
      return route.fulfill({ json: current });
    });
    await page.goto("/admin?tab=environments");
    const panel = page.locator(".application-knowledge");
    await expect(panel).not.toHaveAttribute("open", "");
    await expect(panel.locator("summary").first()).toContainText(t("Business context provided"));
    expect(reads).toBe(0);
    await panel.locator("summary").first().click();
    const presentation = panel.getByLabel(t("Business presentation and vocabulary"), { exact: true });
    await expect(presentation).toHaveValue(current.instructions);
    await expect(presentation).toHaveAttribute("rows", "4");
    await expect(presentation).toHaveAttribute("maxlength", "4000");
    await expect(panel.locator("input[type=file]")).toBeHidden();
    await presentation.fill("Unsaved vocabulary");
    await panel.getByRole("button", { name: t("Add a link"), exact: true }).click();
    const editor = panel.getByRole("group");
    await editor.getByLabel(t("Reference URL or domain"), { exact: true }).fill("https://example.org/new");
    await editor.getByLabel(t("Applicability note (optional)"), { exact: true }).fill("Unsaved reference note");
    await editor.getByRole("button", { name: t("Add"), exact: true }).click();
    const chooser = page.waitForEvent("filechooser");
    await panel.getByRole("button", { name: t("Add a document"), exact: true }).click();
    await (await chooser).setFiles({ name: "procedure.md", mimeType: "text/markdown", buffer: Buffer.from("Fixture procedure") });
    await expect(panel.getByRole("link", { name: "procedure.md", exact: true })).toBeVisible();
    await expect(presentation).toHaveValue("Unsaved vocabulary");
    await expect(panel.getByRole("link", { name: "https://example.org/new", exact: true })).toBeVisible();
    await expect(panel.getByRole("status")).toContainText(t("Text and link changes still need saving."));
    expect(current.instructions).toBe("Declared business vocabulary");
    await panel.locator("summary").first().click();
    await panel.locator("summary").first().click();
    expect(reads).toBe(1);
    await page.getByRole("button", { name: t("Manage Git connections"), exact: true }).click();
    await expect(panel).toBeHidden();
    await page.getByRole("button", { name: t("Configured environments"), exact: true }).click();
    await expect(presentation).toHaveValue("Unsaved vocabulary");
    await panel.getByRole("button", { name: t("Save"), exact: true }).click();
    await expect(panel.getByRole("status")).toHaveText(t("Application knowledge saved."));
    expect(current.instructions).toBe("Unsaved vocabulary");
    expect(current.official_references).toHaveLength(2);
    expect(methods).toEqual(["POST", "PUT"]);
    await panel.getByText(t("Document details"), { exact: true }).first().click();
    await panel.getByText(t("Text preview"), { exact: true }).first().click();
    await expect(panel.locator("pre").first()).toContainText("<script>");
    expect(await page.evaluate(() => (window as Window & { injected?: boolean }).injected)).toBeUndefined();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test("creation stages knowledge, recovers pending uploads and does not create duplicate environments", async ({ page }) => {
  await setup(page, "en");
  const creates: Record<string, unknown>[] = [];
  let uploads = 0;
  let current = { ...configuration(), resources: [] as ReturnType<typeof configuration>["resources"] };
  await page.route("**/api/git-connections**", route => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({ json: path.endsWith("/projects") ? { items: [{ remote_id: "42", path: "team/application", default_branch: "main" }], has_more: false } : path.endsWith("/branches") ? { items: [{ name: "main" }], has_more: false } : [{ id: 7, name: "Fixture source", provider: "github", enabled: true }] });
  });
  await page.route("**/api/environments", route => {
    if (route.request().method() === "POST") { creates.push(route.request().postDataJSON()); return route.fulfill({ status: 201, json: { id: 9 } }); }
    return route.fulfill({ json: [] });
  });
  await page.route("**/api/environments/9/context**", route => {
    if (route.request().method() === "POST") {
      uploads++;
      if (uploads === 1) return route.fulfill({ status: 503, json: { detail: "Fixture upload interrupted" } });
      current = { ...current, revision: 2, resources: configuration().resources };
    }
    return route.fulfill({ json: current });
  });
  await page.goto("/admin?tab=environments");
  await page.getByRole("button", { name: "New environment", exact: true }).click();
  const form = page.locator("#environment-create-form");
  await form.getByLabel("Name", { exact: true }).fill("New fixture");
  await form.getByLabel("Git connection", { exact: true }).selectOption("7");
  await form.getByLabel("Project 1", { exact: true }).selectOption("42");
  await form.getByLabel("Version 1", { exact: true }).selectOption("main");
  const panel = form.locator(".application-knowledge");
  await panel.locator("summary").first().click();
  await panel.getByLabel("Business presentation and vocabulary", { exact: true }).fill("New vocabulary");
  await panel.getByRole("button", { name: "Add a link", exact: true }).click();
  await panel.getByLabel("Reference URL or domain", { exact: true }).fill("https://example.org/guide");
  await panel.getByRole("button", { name: "Add", exact: true }).click();
  await panel.locator("input[type=file]").setInputFiles({ name: "policy.md", mimeType: "text/markdown", buffer: Buffer.from("Fixture policy") });
  await expect(panel.getByText("policy.md", { exact: true })).toBeVisible();
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "The environment is saved." })).toContainText("Some documents still need uploading");
  expect(creates).toHaveLength(1);
  expect(creates[0]).toMatchObject({ context_instructions: "New vocabulary", official_references: [{ url: "https://example.org/guide", note: "" }] });
  await expect(panel.getByLabel("Business presentation and vocabulary", { exact: true })).toBeDisabled();
  await expect(panel.getByText("policy.md", { exact: true })).toBeVisible();
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(form).toHaveCount(0);
  expect(creates).toHaveLength(1);
  expect(uploads).toBe(2);
});
