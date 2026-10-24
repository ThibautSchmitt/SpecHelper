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
    await expect(nav.getByRole("button")).toHaveText(["Connections", "Models", "Roles and orchestration", "Agents", "Skills"].map(t));
    await nav.getByRole("button", { name: t("Skills"), exact: true }).click();
    await page.getByRole("button", { name: t("New skill"), exact: true }).click();
    await page.getByLabel(t("Identifier"), { exact: true }).fill("contract-review");
    await page.getByLabel(t("Name"), { exact: true }).fill("Contract review");
    await page.getByLabel(t("Objective"), { exact: true }).fill("Check contract boundaries.");
    await page.getByLabel(t("Instructions"), { exact: true }).fill("Inspect the existing implementation and cite files.");
    await expect(page.getByRole("group", { name: t("Compatible assistants"), exact: true })).toHaveCount(0);
    await expect(page.getByRole("group", { name: t("Required capabilities"), exact: true })).toHaveCount(0);
    await expect(page.getByLabel(t("Calculated skill metadata"), { exact: true })).toContainText("ChatGPT / Codex, Claude Code");
    await page.getByRole("button", { name: t("Save definition"), exact: true }).click();
    await expect(page.getByRole("status")).toContainText(t("Library definition saved."));
    await expect(page.getByRole("button", { name: t("Delete {name}").replace("{name}", "Contract review"), exact: true })).toBeDisabled();
    await page.getByRole("button", { name: t("Edit {name}").replace("{name}", "Contract review"), exact: true }).click();
    await expect(page.getByLabel(t("Identifier"), { exact: true })).toBeDisabled();
    await page.getByLabel(t("Instructions"), { exact: true }).fill("Refined procedure, preserved historical revision.");
    conflict = true;
    await page.getByRole("button", { name: t("Save definition"), exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(t("The definition has changed. Refresh before editing."));
    await expect(page.getByLabel(t("Instructions"), { exact: true })).toHaveValue("Refined procedure, preserved historical revision.");
    await page.getByRole("button", { name: t("Save definition"), exact: true }).click();
    await expect(page.getByRole("heading", { name: /Contract review/ })).toContainText("v2");
    await page.getByRole("button", { name: t("Versions of {name}").replace("{name}", "Contract review"), exact: true }).click();
    await expect(page.getByRole("heading", { name: t("Versions of {name}").replace("{name}", "Contract review"), exact: true })).toBeVisible();
    const old = page.locator("details").filter({ has: page.locator("summary", { hasText: /^v1/ }) });
    await old.locator("summary").click();
    await expect(old).toContainText("Inspect the existing implementation and cite files.");
    await page.getByRole("button", { name: t("Deactivate {name}").replace("{name}", "Contract review"), exact: true }).click();
    await expect(page.getByRole("button", { name: t("Activate {name}").replace("{name}", "Contract review"), exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Delete {name}").replace("{name}", "Contract review"), exact: true }).click();
    await page.getByRole("group", { name: t("Confirm deletion"), exact: true }).getByRole("button", { name: t("Confirm deletion"), exact: true }).click();
    await expect(page.getByRole("status")).toContainText(t("Definition deleted. Historical versions retained."));
    expect(writes).toBe(5);
    expect(revisions[0].definition.version).toBe(1);
    expect(revisions[0].definition.instructions).toBe("Inspect the existing implementation and cite files.");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await nav.getByRole("button", { name: t("Agents"), exact: true }).click();
    await expect(page.getByRole("heading", { name: t("Agent library"), exact: true })).toBeVisible();
    await page.getByRole("button", { name: t("Edit {name}").replace("{name}", "Source analysis"), exact: true }).click();
    await expect(page.getByRole("group", { name: t("Required skills"), exact: true })).toBeVisible();
    expect(await page.locator("article").filter({ has: page.getByRole("heading", { name: /Source analysis/ }) }).getByRole("heading").evaluate(node => node.getBoundingClientRect().width)).toBeGreaterThan(100);
    await page.screenshot({ path: `../.local/v20-evidence/library-${language}-${info.project.name}.png`, fullPage: true });
  });

  test(`environment preview checks unsaved references and invalidates after changes in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    const t = (key: string) => text(language, key);
    const skill = definition("contract-review", "Contract review");
    await page.route("**/api/library/agent", route => route.fulfill({ json: agents }));
    await page.route("**/api/library/skill", route => route.fulfill({ json: [skill] }));
    let selection = { revision: 1, agents: null as string[] | null, skills: null as string[] | null };
    let checked: Record<string, unknown> | null = null;
    let saved: Record<string, unknown> | null = null;
    let compatible = false;
    await page.route("**/api/environments/1/library", async route => {
      if (route.request().method() === "PUT") {
        saved = route.request().postDataJSON();
        expect(saved).not.toHaveProperty("instructions");
        selection = { revision: 2, agents: saved!.agents as string[] | null, skills: saved!.skills as string[] | null };
      }
      return route.fulfill({ json: selection });
    });
    await page.route("**/api/environments/1/library/preview?*", async route => {
      expect(route.request().method()).toBe("POST");
      expect(new URL(route.request().url()).searchParams.get("connection_id")).toBe("1");
      checked = route.request().postDataJSON();
      return route.fulfill({ json: { compatible, incompatibilities: compatible ? [] : [{ slug: skill.slug, kind: "skill", reason: "Provider incompatibility" }], instructions: "Portable procedure, no new permissions.", library: { agents, skills: [skill] }, provider: "codex" } });
    });
    await page.goto("/admin");
    await page.getByRole("button", { name: t("Environments"), exact: true }).click();
    await page.getByText(t("Agents and skills for this environment"), { exact: true }).click();
    const section = page.locator("details").filter({ has: page.locator("summary", { hasText: t("Agents and skills for this environment") }) });
    await expect(section.getByRole("button", { name: t("Save environment selection"), exact: true })).toBeDisabled();
    await section.getByRole("group", { name: t("Skills"), exact: true }).getByRole("checkbox", { name: t("Inherit all active definitions"), exact: true }).uncheck();
    await section.getByLabel(t("Preview with an AI connection"), { exact: true }).selectOption("1");
    await section.getByRole("button", { name: t("Preview effective configuration"), exact: true }).click();
    await expect(section.getByRole("status")).toContainText(t("Provider incompatibility"));
    expect(checked).toMatchObject({ expected_revision: 1, agents: null, skills: ["contract-review"] });
    await expect(section.getByRole("button", { name: t("Save environment selection"), exact: true })).toBeDisabled();
    compatible = true;
    await section.getByRole("button", { name: t("Preview effective configuration"), exact: true }).click();
    await expect(section.getByRole("heading", { name: t("Compatible configuration"), exact: true })).toBeVisible();
    await expect(section.getByRole("button", { name: t("Save environment selection"), exact: true })).toBeEnabled();
    await section.getByRole("checkbox", { name: /Contract review/ }).uncheck();
    await expect(section.getByRole("button", { name: t("Save environment selection"), exact: true })).toBeDisabled();
    await expect(section.getByRole("heading", { name: t("Compatible configuration"), exact: true })).toHaveCount(0);
    await section.getByRole("button", { name: t("Preview effective configuration"), exact: true }).click();
    await expect(section.getByRole("button", { name: t("Save environment selection"), exact: true })).toBeEnabled();
    await section.getByRole("button", { name: t("Save environment selection"), exact: true }).click();
    await expect(section.getByRole("status")).toContainText(t("Environment library selection saved."));
    expect(saved).toEqual({ expected_revision: 1, agents: null, skills: [] });
    expect(await section.evaluate(node => Array.from(node.querySelectorAll("button,select")).every(control => control.getBoundingClientRect().right <= node.getBoundingClientRect().right + 1))).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.local/v20-evidence/environment-library-${language}-${info.project.name}.png`, fullPage: true });
  });
}
