import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";

for (const language of ["en", "fr"] as const) {
  test(`repository/version favorites persist and environment copies remain editable in ${language}`, async ({ page }, info) => {
    const t = (key: string) => translate(key, language);
    await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "fr" ? "dark" : "light");
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language } }));
    await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4" } }));
    await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [{ id: 4, name: "Readonly DB" }], github: { status: "DISCONNECTED" } } }));
    const project = { id: 77, remote_id: "77", path: "team/api", default_branch: "main", is_fork: false, parent: null };
    const environment = { id: 8, name: "Staging", revision: 3, status: "READY", error: "", database_id: 4, database_name: "Readonly DB", publication_connection_ids: [], repositories: [{ ...project, repository: "internal/api", git_connection_id: 9, branch: "tag:release/v1", sha: "a".repeat(40) }] };
    await page.route("**/api/environments", route => {
      if (route.request().method() === "POST") return route.fulfill({ status: 201, json: { ...environment, id: 10, name: "Preview", status: "PENDING" } });
      return route.fulfill({ json: [environment] });
    });
    await page.route("**/api/git-connections", route => route.fulfill({ json: [9, 10].map(id => ({ id, name: `Source ${id}`, provider: "gitlab", enabled: true, status: "CONNECTED" })) }));
    let discoveryHasFavorite = true;
    await page.route("**/api/git-connections/*/projects?**", route => route.fulfill({ json: { items: discoveryHasFavorite ? [project] : [], has_more: false } }));
    await page.route("**/api/git-connections/*/branches?**", route => route.fulfill({ json: { items: discoveryHasFavorite ? [{ name: "release/v1", ref: "tag:release/v1" }, { name: "main", ref: "main" }] : [{ name: "main", ref: "main" }], has_more: false } }));
    let favorite = { ...project, git_connection_id: 9, favorite: false, favorite_refs: [] as string[] };
    await page.route("**/api/git-favorites", route => route.fulfill({ json: [favorite] }));
    const mutations: unknown[] = [];
    await page.route("**/api/git-connections/9/favorites", route => {
      const body = route.request().postDataJSON();
      mutations.push(body);
      if (body.reference) favorite = { ...favorite, favorite_refs: body.favorite ? [...new Set([...favorite.favorite_refs, body.reference])] : favorite.favorite_refs.filter(ref => ref !== body.reference) };
      else favorite = { ...favorite, favorite: body.favorite };
      return route.fulfill({ json: favorite });
    });
    await page.goto("/admin?tab=environments");
    const card = page.locator(".environment-card");
    await card.getByRole("button", { name: t("Edit {name}").replace("{name}", "Staging"), exact: true }).click();
    let editor = page.getByRole("region", { name: t("Edit environment"), exact: true });
    await editor.getByRole("button", { name: t("Add project to favorites"), exact: true }).click();
    await expect(editor.getByRole("button", { name: t("Remove project from favorites") })).toHaveAttribute("aria-pressed", "true");
    await editor.getByRole("button", { name: t("Add version to favorites"), exact: true }).click();
    await expect(editor.getByRole("button", { name: t("Remove version from favorites") })).toHaveAttribute("aria-pressed", "true");
    expect(mutations).toEqual([{ remote_id: "77", reference: "", favorite: true }, { remote_id: "77", reference: "tag:release/v1", favorite: true }]);
    // Favorites remain reachable even when absent from the current discovery page.
    discoveryHasFavorite = false;
    await page.reload();
    await card.getByRole("button", { name: t("Edit {name}").replace("{name}", "Staging"), exact: true }).click();
    editor = page.getByRole("region", { name: t("Edit environment"), exact: true });
    await expect(editor.locator('select[id$="-repository"] optgroup').first()).toHaveAttribute("label", t("Favorites"));
    await expect(editor.locator('select[id$="-branch"] optgroup').first()).toHaveAttribute("label", t("Favorites"));
    await expect(editor.locator('select[id$="-repository"] option[value="77"]')).toHaveCount(1);
    await expect(editor.locator('select[id$="-branch"] option[value="tag:release/v1"]')).toHaveCount(1);
    await editor.locator('select[id$="-connection"]').selectOption("10");
    await expect(editor.locator('optgroup[label="' + t("Favorites") + '"]')).toHaveCount(0);
    await editor.getByRole("button", { name: t("Cancel"), exact: true }).click();
    const writes: unknown[] = [];
    await page.route("**/api/environments", route => {
      if (route.request().method() === "POST") {
        writes.push(route.request().postDataJSON());
        return route.fulfill({ status: 201, json: { ...environment, id: 10, name: "Preview", status: "PENDING" } });
      }
      return route.fulfill({ json: [environment] });
    });
    await card.getByLabel(t("More actions for {name}").replace("{name}", "Staging"), { exact: true }).click();
    await card.getByRole("button", { name: t("Duplicate {name}").replace("{name}", "Staging"), exact: true }).click();
    const copy = page.getByRole("region", { name: t("Duplicate environment"), exact: true });
    await expect(copy.getByLabel(t("Environment name"), { exact: true })).toHaveValue(t("{name} (copy)").replace("{name}", "Staging"));
    expect(writes).toHaveLength(0);
    await copy.getByLabel(t("Environment name"), { exact: true }).fill("Preview");
    await copy.locator('select[id$="-ref-kind"]').selectOption("branch");
    await copy.locator('select[id$="-branch"]').selectOption("main");
    await copy.screenshot({ path: `../.local/environment-copy-${language}-${info.project.name}.png` });
    await copy.getByRole("button", { name: t("Create copy"), exact: true }).click();
    await expect(copy).not.toBeVisible();
    expect(writes).toEqual([{ name: "Preview", copy_from_environment_id: 8, expected_source_revision: 3, database_id: 4, publication_connection_ids: [], repositories: [{ git_connection_id: 9, remote_id: "77", branch: "main" }] }]);
    await expect(card.getByRole("heading", { name: "Staging", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
