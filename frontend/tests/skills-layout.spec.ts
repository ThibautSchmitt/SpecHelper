import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";
import type { Page } from "@playwright/test";
import type { LibraryDefinition } from "../src/components/ai-library";

const definition = (slug: string, name: string, built_in = false): LibraryDefinition => ({
  slug, name, objective: built_in ? "Find and verify the behavior in inspected sources." : "A reusable team procedure.",
  instructions: "Read the frozen sources.\n" + "Preserve conditions and exceptions.\n".repeat(20),
  enabled: true, compatibility: [], required_capabilities: [], expected_checks: [], version: 4, deleted: false, built_in,
});
const builtins = [
  ["attachment-analysis", "Document analysis"], ["codebase-navigation", "Code and source exploration"],
  ["data-protection", "Data protection"], ["impact-analysis", "Impact analysis"],
].map(([slug, name]) => definition(slug, name, true));

async function setup(page: Page, language: "en" | "fr", theme: string) {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [] } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4" } }));
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), theme);
}

for (const language of ["en", "fr"] as const) for (const theme of ["light", "dark"]) {
  const t = (key: string, parameters: Record<string, string | number> = {}) => translate(key, language, parameters);
  test(`compact skill library and protected drawer edits in ${language} ${theme}`, async ({ page }, info) => {
    await setup(page, language, theme);
    let items = [...builtins, definition("team-review", "Team review")];
    const writes: Record<string, unknown>[] = [];
    let conflict = false;
    await page.route("**/api/library/skill", route => {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON(); writes.push(body);
        items.push({ ...body, version: 1, deleted: false, built_in: false });
        return route.fulfill({ status: 201, json: items.at(-1) });
      }
      return route.fulfill({ json: items });
    });
    await page.route("**/api/library/skill/team-review", route => {
      const body = route.request().postDataJSON(); writes.push(body);
      if (conflict) { conflict = false; return route.fulfill({ status: 409, json: { detail: "The definition has changed. Refresh before editing." } }); }
      items = items.map(item => item.slug === "team-review" ? { ...item, ...body, version: item.version + 1 } : item);
      return route.fulfill({ json: items.at(-1) });
    });
    await page.goto("/admin?tab=ai-agents&section=skills");
    const library = page.getByRole("region", { name: t("Skills"), exact: true });
    await expect(library).toHaveAttribute("data-slot", "card");
    expect(await library.evaluate(node => parseFloat(getComputedStyle(node).borderTopWidth))).toBeGreaterThan(0);
    expect(await library.evaluate(node => parseFloat(getComputedStyle(node).paddingLeft))).toBeGreaterThan(0);
    await expect(library.locator("[data-slot=card]")).toHaveCount(0);
    await expect(library.locator("[data-builtin-skill]")).toHaveCount(4);
    const customHeading = await library.getByRole("heading", { name: t("Custom skills"), exact: true }).boundingBox();
    const builtinHeading = await library.getByRole("heading", { name: t("Built-in skills"), exact: true }).boundingBox();
    expect(customHeading!.y).toBeLessThan(builtinHeading!.y);
    for (const [index, item] of builtins.entries()) {
      const row = library.locator("[data-builtin-skill]").nth(index);
      await expect(row.locator("pre")).toBeHidden();
      await expect(row.getByRole("button")).toHaveCount(0);
      await row.locator("summary").click();
      await expect(row.locator("pre")).toHaveText(item.instructions);
      await row.locator("summary").click();
      await expect(row.getByText(/^v\d+$/)).toHaveCount(0);
    }
    const search = library.getByLabel(t("Search skills"), { exact: true });
    await search.fill(t("Code and source exploration"));
    await expect(library.locator("[data-builtin-skill]")).toHaveCount(1);
    await search.fill("no-matching-procedure");
    await expect(library.getByText(t("No matching skills."), { exact: true })).toBeVisible();
    await search.fill("");
    if (info.project.name === "desktop") expect((await search.boundingBox())!.width).toBeLessThan(400);
    await library.screenshot({ path: `../.local/skills-ui/list-${language}-${theme}-${info.project.name}.png` });
    const add = library.getByRole("button", { name: t("Add skill"), exact: true });
    await add.click();
    const drawer = page.getByRole("dialog", { name: t("New skill"), exact: true });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByLabel(t("Identifier"), { exact: true })).toBeFocused();
    expect(await library.locator("form").evaluate(node => !!node.closest("dialog"))).toBe(true);
    await expect(drawer.getByRole("button", { name: t("Save"), exact: true })).toBeInViewport();
    await drawer.screenshot({ path: `../.local/skills-ui/drawer-${language}-${theme}-${info.project.name}.png` });
    await drawer.getByLabel(t("Name"), { exact: true }).fill("Keep this draft");
    page.once("dialog", dialog => dialog.dismiss());
    await drawer.press("Escape");
    await expect(drawer.getByLabel(t("Name"), { exact: true })).toHaveValue("Keep this draft");
    page.once("dialog", dialog => dialog.accept());
    await drawer.getByRole("button", { name: t("Cancel"), exact: true }).click();
    await expect(drawer).toHaveCount(0);
    await expect(add).toBeFocused();
    const row = library.getByRole("article", { name: "Team review", exact: true });
    await row.getByRole("button", { name: t("Edit {name}", { name: "Team review" }), exact: true }).click();
    const editor = page.getByRole("dialog", { name: t("Edit skill"), exact: true });
    await editor.getByLabel(t("Instructions"), { exact: true }).fill("Changed procedure with preserved evidence.");
    conflict = true;
    await editor.getByRole("button", { name: t("Save"), exact: true }).click();
    await expect(editor.getByRole("alert")).toContainText(t("The definition has changed. Refresh before editing."));
    await expect(editor.getByLabel(t("Instructions"), { exact: true })).toHaveValue("Changed procedure with preserved evidence.");
    await editor.getByRole("button", { name: t("Save"), exact: true }).click();
    await expect(editor).toHaveCount(0);
    expect(writes.at(-1)).toMatchObject({ expected_version: 4, instructions: "Changed procedure with preserved evidence." });
    await expect(library.getByRole("status")).toContainText(t("Library definition saved."));
    await add.click();
    await drawer.getByLabel(t("Identifier"), { exact: true }).fill("new-procedure");
    await drawer.getByLabel(t("Name"), { exact: true }).fill("New procedure");
    await drawer.getByLabel(t("Objective"), { exact: true }).fill("A clear purpose");
    await drawer.getByLabel(t("Instructions"), { exact: true }).fill("Inspect the sources safely.");
    await drawer.getByRole("button", { name: t("Save"), exact: true }).click();
    await expect(drawer).toHaveCount(0);
    await expect(library.getByRole("article", { name: "New procedure", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(key, language);
  test(`JSON import and generated proposals require review in ${language}`, async ({ page }) => {
    await setup(page, language, "light");
    let items = [...builtins]; let imports = 0, generated = 0, draftSaves = 0, activations = 0;
    const proposal = { ...definition("generated-review", "Generated review"), enabled: false };
    const generatedDraft = { id: "draft-1", kind: "skill", status: "PROPOSED", revision: 1, connection_id: 1, definition: proposal,
      messages: [{ role: "assistant", content: "A proposed procedure for review.", questions: [] }], validation: { valid: true, errors: [] }, recommendations: [], job: null, test_result: null, activated_definition: null, updated_at: "2026-11-02T05:00:00Z" };
    await page.route("**/api/library/skill", route => route.fulfill({ json: items }));
    await page.route("**/api/ai-connections", route => route.fulfill({ json: [{ id: 1, name: "Fixture assistant", agent: "codex", enabled: true, status: "CONNECTED", availability: "AVAILABLE" }] }));
    await page.route("**/api/library/import/preview", route => route.fulfill({ json: { valid: true, errors: [], definition: proposal } }));
    await page.route("**/api/library/import", route => {
      imports++; items = [...items, { ...proposal, name: "Imported review" }];
      return route.fulfill({ json: { imported: true } });
    });
    await page.route("**/api/library-assistant/drafts", route => {
      if (route.request().method() === "POST") { generated++; return route.fulfill({ json: generatedDraft }); }
      return route.fulfill({ json: [] });
    });
    await page.route("**/api/library-assistant/drafts/draft-1", route => {
      draftSaves++; generatedDraft.definition = route.request().postDataJSON().definition; generatedDraft.revision++;
      return route.fulfill({ json: generatedDraft });
    });
    await page.route("**/api/library-assistant/drafts/draft-1/activate", route => {
      activations++; return route.fulfill({ json: { ...generatedDraft, status: "ACTIVE" } });
    });
    await page.goto("/admin?tab=ai-agents&section=skills");
    const library = page.getByRole("region", { name: t("Skills"), exact: true });
    await expect(library.getByText(t("No custom skills."), { exact: true })).toBeVisible();
    await library.getByRole("button", { name: t("Import skill"), exact: true }).click();
    const importer = page.getByRole("dialog", { name: t("Import skill"), exact: true });
    await importer.getByLabel(t("Definition JSON"), { exact: true }).fill("{ invalid");
    await importer.getByRole("button", { name: t("Validate import"), exact: true }).click();
    await expect(importer.getByRole("alert")).toContainText(t("Enter a valid JSON definition."));
    await importer.locator("input[type=file]").setInputFiles({ name: "procedure.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify({ schema_version: 1, kind: "skill", definition: proposal })) });
    await importer.getByRole("button", { name: t("Validate import"), exact: true }).click();
    expect(imports).toBe(0);
    await importer.getByRole("button", { name: t("Import as draft"), exact: true }).click();
    await expect(importer).toHaveCount(0);
    expect(imports).toBe(1);
    await library.getByRole("button", { name: t("Generate with AI"), exact: true }).click();
    const generator = page.getByRole("dialog", { name: t("Generate with AI"), exact: true });
    await generator.getByLabel(t("What should this definition help with?"), { exact: true }).fill("Inspect the project's conditions.");
    await generator.getByRole("button", { name: t("Start generation"), exact: true }).click();
    await expect(generator.getByLabel(t("Name"), { exact: true })).toHaveValue("Generated review");
    expect(generated).toBe(1); expect(activations).toBe(0);
    await generator.getByLabel(t("Instructions"), { exact: true }).fill("Refined proposal, awaiting approval.");
    page.once("dialog", dialog => dialog.dismiss());
    await generator.press("Escape");
    await expect(generator.getByLabel(t("Instructions"), { exact: true })).toHaveValue("Refined proposal, awaiting approval.");
    await generator.getByRole("button", { name: t("Save as draft"), exact: true }).click();
    await expect(generator.getByRole("button", { name: t("Activate"), exact: true })).toBeEnabled();
    expect(draftSaves).toBe(1); expect(activations).toBe(0);
    await generator.getByRole("button", { name: t("Activate"), exact: true }).click();
    expect(activations).toBe(0);
    await generator.getByRole("button", { name: t("Confirm activation"), exact: true }).click();
    await expect(generator.getByText(t("Definition activated in the shared library."), { exact: true })).toBeVisible();
    expect(activations).toBe(1);
  });
}
