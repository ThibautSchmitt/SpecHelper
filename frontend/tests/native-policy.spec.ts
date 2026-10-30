import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(key, language);
  test(`native policy hides prompt and call editors while protecting built-in skills in ${language}`, async ({ page }) => {
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { authenticated: true, mode: "local" } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { language, name: "SpecHelper", primary_color: "#2563eb" } }));
    await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [] } }));
    await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4", max_calls: 20, allow_same_family_fallback: true, role_coverage: { complete: false, roles: Object.fromEntries(["analyst", "counter_analyst", "verifier"].map(role => [role, { configured: [], available: [] }])) } } }));
    const native = { slug: "codebase-navigation", name: "Native navigation", objective: "Find inspected sources", instructions: "Read the actual frozen sources.", enabled: true, built_in: true, version: 2, deleted: false, compatibility: [], required_capabilities: ["read_sources"], expected_checks: [] };
    let custom = { ...native, slug: "team-procedure", name: "Team procedure", built_in: false, version: 1 };
    await page.route("**/api/library/skill", route => route.fulfill({ json: [custom, native] }));
    await page.route("**/api/library/skill/codebase-navigation/versions", route => route.fulfill({ json: [1, 2].map(version => ({ version, definition: { ...native, version }, action: "imported", editor: "system", created_at: "2026-10-29T00:00:00Z" })) }));
    let submitted: Record<string, unknown> | null = null;
    await page.route("**/api/library/skill/team-procedure", route => {
      submitted = route.request().postDataJSON();
      custom = { ...custom, ...submitted, version: 2 };
      return route.fulfill({ json: custom });
    });
    await page.goto("/admin");
    await expect(page.getByLabel(t("Global instructions"), { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: t("Save global instructions"), exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    const nav = page.getByRole("navigation", { name: t("AI settings"), exact: true });
    await nav.getByRole("button", { name: t("Orchestration"), exact: true }).click();
    await expect(page.getByLabel(t("Maximum AI calls per analysis"), { exact: true })).toHaveCount(0);
    await expect(page.getByText(t("Instruction hierarchy"), { exact: true })).toHaveCount(0);
    await expect(page.getByText(t("Automatic safeguards stop stalled or repeated steps and preserve completed observations."), { exact: true })).toBeVisible();
    await nav.getByRole("button", { name: t("Skills"), exact: true }).click();
    await expect(page.getByRole("heading", { name: t("Built-in skills"), exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: t("Custom skills"), exact: true })).toBeVisible();
    const builtin = page.getByRole("article", { name: native.name, exact: true });
    await expect(builtin.getByRole("button", { name: t("Edit {name}").replace("{name}", native.name), exact: true })).toHaveCount(0);
    await builtin.getByText(t("View instructions"), { exact: true }).click();
    await expect(builtin).toContainText(native.instructions);
    await builtin.getByLabel(t("More actions for {name}").replace("{name}", native.name), { exact: true }).click();
    await expect(builtin.getByRole("button", { name: t("Deactivate {name}").replace("{name}", native.name), exact: true })).toHaveCount(0);
    await expect(builtin.getByRole("button", { name: t("Delete {name}").replace("{name}", native.name), exact: true })).toHaveCount(0);
    await builtin.getByRole("button", { name: t("Versions of {name}").replace("{name}", native.name), exact: true }).click();
    await expect(page.getByRole("button", { name: /Restore version|Restaurer la version/ })).toHaveCount(0);
    const own = page.getByRole("article", { name: custom.name, exact: true });
    await own.getByRole("button", { name: t("Edit {name}").replace("{name}", custom.name), exact: true }).click();
    await page.getByLabel(t("Name"), { exact: true }).fill("Reviewed team procedure");
    await page.getByRole("button", { name: t("Save skill"), exact: true }).click();
    await expect.poll(() => submitted?.name).toBe("Reviewed team procedure");
    expect(submitted).not.toHaveProperty("built_in");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
