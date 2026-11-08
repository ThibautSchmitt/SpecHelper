import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import type { LibraryDefinition } from "../src/components/ai-library";
import english from "../src/locales/en.json";
import french from "../src/locales/fr.json";

const definition = (slug: string, name: string): LibraryDefinition => ({ slug, name, objective: `Objective for ${name}`, instructions: `Instructions for ${name}`, enabled: true, compatibility: [], required_capabilities: [], version: 1, deleted: false, skills: [] });
const agents = [definition("requirement", "Requirement"), definition("code", "Source analysis"), definition("writer", "Writing")];
const text = (language: "en" | "fr", key: string) => (language === "fr" ? french : english)[key as keyof typeof english] || key;
async function setup(page: Page, language: "en" | "fr") {
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "fr" ? "dark" : "light");
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, short_label: "", primary_color: "#2563eb", allow_confrontation: true } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { github: { status: "CONNECTED" }, ais: [], databases: [] } }));
  await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Production", status: "READY", repositories: [], revision: 1 }] }));
  await page.route("**/api/queue", route => route.fulfill({ json: [] }));
  await page.route("**/api/system", route => route.fulfill({ json: { jobs: [] } }));
  await page.route("**/api/ticket-connectors*", route => route.fulfill({ json: [] }));
  await page.route("**/api/environments/1/context", route => route.fulfill({ json: { instructions: "", instructions_enabled: true, revision: 1, resources: [], max_files: 20, max_file_size: 26214400 } }));
  await page.route("**/api/ai-models*", route => route.fulfill({ json: { items: [], discovery: { state: "unknown", reason: "" } } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { verifier_enabled: true, allow_same_family_fallback: true, allow_confrontation: true, max_calls: 10, timeout_seconds: 285, role_instructions: {}, active_internal_agents: agents.map(item => item.slug), default_skills: [], available_agents: agents, available_skills: [] } }));
}
for (const language of ["en", "fr"] as const) {
  test(`versioned library supports edits, conflicts, audit and protected deletion in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const t = (key: string) => text(language, key);
    let skills: LibraryDefinition[] = [];
    const revisions: { version: number; definition: LibraryDefinition; action: string; editor: string; created_at: string }[] = [];
    let writes = 0;
    let conflict = false;
    await page.route("**/api/library/**", async route => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/library/agent") return route.fulfill({ json: agents });
      if (url.pathname.endsWith("/versions")) return route.fulfill({ json: [...revisions].reverse() });
      const method = route.request().method();
      if (method === "GET") return route.fulfill({ json: skills });
      writes += 1;
      if (conflict) { conflict = false; return route.fulfill({ status: 409, json: { detail: "The definition has changed. Refresh before editing." } }); }
      if (method === "DELETE") {
        expect(url.searchParams.get("expected_version")).toBe("3");
        skills = []; return route.fulfill({ json: { deleted: true, historical_versions_retained: true } });
      }
      const payload = route.request().postDataJSON();
      const item = { ...payload, version: method === "POST" ? 1 : payload.expected_version + 1, deleted: false };
      skills = [item];
      revisions.push({ version: item.version, definition: structuredClone(item), action: method === "POST" ? "created" : "edited", editor: "administrator", created_at: "2026-10-23T10:00:00Z" });
      return route.fulfill({ json: item });
    });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    const nav = page.getByRole("navigation", { name: t("AI settings"), exact: true });
    await expect(nav.getByRole("button")).toHaveText(["Connections", "Orchestration", "Skills"].map(t));
    await nav.getByRole("button", { name: t("Skills"), exact: true }).click();
    await page.getByRole("button", { name: t("Add skill"), exact: true }).click();
    await page.getByLabel(t("Identifier"), { exact: true }).fill("contract-review");
    await page.getByLabel(t("Name"), { exact: true }).fill("Contract review");
    await page.getByLabel(t("Objective"), { exact: true }).fill("Check contract boundaries.");
    await page.getByLabel(t("Instructions"), { exact: true }).fill("Inspect the existing implementation and cite files.");
    await expect(page.getByRole("group", { name: t("Compatible assistants"), exact: true })).toHaveCount(0);
    await expect(page.getByRole("group", { name: t("Required capabilities"), exact: true })).toHaveCount(0);
    await expect(page.getByLabel(t("Calculated skill metadata"), { exact: true })).toContainText("ChatGPT / Codex, Claude Code");
    await page.getByRole("button", { name: t("Save skill"), exact: true }).click();
    await expect(page.getByRole("status")).toContainText(t("Library definition saved."));
    await page.getByLabel(t("More actions for {name}").replace("{name}", "Contract review"), { exact: true }).click();
    await expect(page.getByRole("button", { name: t("Delete {name}").replace("{name}", "Contract review"), exact: true })).toBeDisabled();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: t("Edit {name}").replace("{name}", "Contract review"), exact: true }).click();
    await expect(page.getByLabel(t("Identifier"), { exact: true })).toBeDisabled();
    await page.getByLabel(t("Instructions"), { exact: true }).fill("Refined procedure, preserved historical revision.");
    conflict = true;
    await page.getByRole("button", { name: t("Save"), exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(t("The definition has changed. Refresh before editing."));
    await expect(page.getByLabel(t("Instructions"), { exact: true })).toHaveValue("Refined procedure, preserved historical revision.");
    await page.getByRole("button", { name: t("Save"), exact: true }).click();
    expect(revisions.at(-1)?.version).toBe(2);
    await page.getByLabel(t("More actions for {name}").replace("{name}", "Contract review"), { exact: true }).click();
    await page.getByRole("button", { name: t("Versions of {name}").replace("{name}", "Contract review"), exact: true }).click();
    await expect(page.getByRole("heading", { name: t("Versions of {name}").replace("{name}", "Contract review"), exact: true })).toBeVisible();
    const old = page.locator("details").filter({ has: page.locator("summary", { hasText: /^v1/ }) });
    await old.locator("summary").click();
    await expect(old).toContainText("Inspect the existing implementation and cite files.");
    await page.getByLabel(t("More actions for {name}").replace("{name}", "Contract review"), { exact: true }).click();
    await page.getByRole("button", { name: t("Deactivate {name}").replace("{name}", "Contract review"), exact: true }).click();
    await page.getByLabel(t("More actions for {name}").replace("{name}", "Contract review"), { exact: true }).click();
    await expect(page.getByRole("button", { name: t("Activate {name}").replace("{name}", "Contract review"), exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Delete {name}").replace("{name}", "Contract review"), exact: true }).click();
    await page.getByRole("group", { name: t("Confirm deletion"), exact: true }).getByRole("button", { name: t("Confirm deletion"), exact: true }).click();
    await expect(page.getByRole("status")).toContainText(t("Definition deleted. Historical versions retained."));
    expect(writes).toBe(5);
    expect(revisions[0].definition.version).toBe(1);
    expect(revisions[0].definition.instructions).toBe("Inspect the existing implementation and cite files.");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(nav.getByRole("button", { name: t("Agents"), exact: true })).toHaveCount(0);
  });

  test(`skills remain global without per-environment selection in ${language}`, async ({ page }) => {
    await setup(page, language);
    const t = (key: string) => text(language, key);
    const reads: string[] = [];
    await page.route("**/api/library/skill", route => route.fulfill({ json: [definition("contract-review", "Contract review")] }));
    await page.route("**/api/environments/1/library**", route => {
      reads.push(route.request().url());
      return route.fulfill({ json: { revision: 1, agents: null, skills: null } });
    });
    await page.goto("/admin?tab=environments");
    await expect(page.getByText(t("Agents and skills for this environment"), { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
    await page.getByRole("button", { name: t("Skills"), exact: true }).click();
    await expect(page.getByRole("article", { name: "Contract review", exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("article", { name: "Contract review", exact: true })).toBeVisible();
    expect(reads).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
