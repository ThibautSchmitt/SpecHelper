import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import { translate } from "../src/lib/i18n";

async function setup(page: Page, language: "en" | "fr") {
  const roles = ["analyst", "counter_analyst", "verifier"];
  const skill = (slug: string) => ({ slug, name: `Skill ${slug}`, objective: `Objective ${slug}`, instructions: `Instructions ${slug}`, enabled: false, compatibility: [], required_capabilities: [], version: 1, deleted: false, skills: [] });
  const writes: string[] = [];
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname.slice(4);
    if (route.request().method() !== "GET") writes.push(path);
    let json: unknown = [];
    if (path === "/access/session") json = { mode: "local", authenticated: true };
    if (path === "/settings") json = { name: "SpecHelper", language, primary_color: "#168e95" };
    if (path === "/connections") json = { ais: [], databases: [], github: { status: "DISCONNECTED" } };
    if (path === "/orchestration-settings") json = { reliability_protocol: "2.4", allow_same_family_fallback: true, role_coverage: { complete: true, roles: Object.fromEntries(roles.map(role => [role, { configured: [1], available: [] }])) } };
    if (path === "/ai-connections") json = [{ id: 1, name: "ChatGPT", agent: "codex", model: "test-model", enabled: true, status: "CONNECTED", availability: "QUOTA_EXHAUSTED", roles, quota_windows: { weekly: { exhausted: true, remaining_percent: 0, observed_at: new Date().toISOString() } } }];
    if (path === "/library/skill") json = [skill("first"), skill("second")];
    return route.fulfill({ json });
  });
  return writes;
}

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => translate(key, language);
  test(`settings headings keep add actions on the right and quota next to Edit in ${language}`, async ({ page }) => {
    test.setTimeout(90_000);
    await setup(page, language);
    for (const [url, section, add] of [
      ["/admin?tab=environments", "Environments", "New environment"],
      ["/admin?tab=environments&sources=git", "Git sources", "New Git connection"],
      ["/admin?tab=environments&sources=postgres", "PostgreSQL connections", "Add connection"],
      ["/admin?tab=connectors", "Publication connections", "New connector"],
      ["/admin?tab=ai-agents&section=skills", "Skills", "Add skill"],
    ]) {
      await page.goto(url);
      const region = page.getByRole("region", { name: t(section), exact: true });
      const header = region.locator(".section-heading").first();
      await expect(header.getByRole("heading", { level: 2 })).toBeVisible();
      const button = header.getByRole("button", { name: t(add), exact: true });
      await expect(button).toBeVisible();
      await expect(button.locator("svg")).toBeVisible();
      const box = (await header.boundingBox())!;
      const action = (await button.boundingBox())!;
      expect(Math.abs(box.x + box.width - action.x - action.width)).toBeLessThan(2);
      await expect(region.locator("p.muted").first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (language === "fr") await page.screenshot({ path: `../.local/inline-ui/${test.info().project.name}-${section.replaceAll(" ", "-")}.png` });
    }
    await page.goto("/admin?tab=ai-agents&section=roles");
    const orchestration = page.getByRole("region", { name: t("Orchestration"), exact: true });
    await expect(orchestration.locator(".section-heading").getByRole("heading", { name: t("Orchestration"), exact: true })).toBeVisible();
    await expect(orchestration.locator(".section-heading").getByRole("button")).toHaveCount(0);
    await expect(orchestration.locator('[data-slot="card"]')).toBeVisible();
    await page.goto("/admin?tab=ai-agents&section=connections");
    const account = page.locator(".ai-connection-card").filter({ has: page.getByRole("heading", { name: "ChatGPT", exact: true }) });
    const quota = account.locator(".connection-quota-exhausted");
    const edit = account.getByRole("button", { name: t("Edit"), exact: true });
    await expect(quota).toBeVisible();
    await edit.click();
    await expect(account.locator("[data-editor-actions]").getByRole("button")).toHaveText([t("Cancel"), t("Save")]);
    await edit.click();
    expect(await quota.evaluate(node => node.nextElementSibling?.getAttribute("aria-label"))).toBe(t("Edit"));
    const badge = (await quota.boundingBox())!, button = (await edit.boundingBox())!;
    expect(badge.x + badge.width).toBeLessThanOrEqual(button.x);
    expect(Math.abs(badge.y + badge.height / 2 - button.y - button.height / 2)).toBeLessThan(2);
    if (language === "fr") await page.screenshot({ path: `../.local/inline-ui/${test.info().project.name}-quota.png` });
  });

  test(`custom skill editors stay inside the selected card and close without saving in ${language}`, async ({ page }) => {
    const writes = await setup(page, language);
    await page.goto("/admin?tab=ai-agents&section=skills");
    const first = page.getByRole("article", { name: "Skill first", exact: true });
    const second = page.getByRole("article", { name: "Skill second", exact: true });
    const editFirst = first.getByRole("button", { name: t("Edit {name}").replace("{name}", "Skill first"), exact: true });
    await editFirst.click();
    await expect(editFirst).toHaveAttribute("aria-expanded", "true");
    await expect(first.locator("[data-editor-actions]").getByRole("button")).toHaveText([t("Cancel"), t("Save")]);
    await first.getByLabel(t("Instructions"), { exact: true }).fill("Unsaved instructions");
    await second.getByRole("button", { name: t("Edit {name}").replace("{name}", "Skill second"), exact: true }).click();
    await expect(first.locator("form")).toHaveCount(0);
    await expect(second.getByLabel(t("Instructions"), { exact: true })).toHaveValue("Instructions second");
    await editFirst.click();
    await expect(first.getByLabel(t("Instructions"), { exact: true })).toHaveValue("Instructions first");
    await editFirst.click();
    await expect(first.locator("form")).toHaveCount(0);
    await expect(editFirst).toHaveAttribute("aria-expanded", "false");
    expect(writes).toEqual([]);
  });

  test(`Git and publication cards use the AI surface and top-right actions in ${language}`, async ({ page }) => {
    const theme = language === "en" ? "light" : "dark";
    await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), theme);
    await setup(page, language);
    await page.goto("/admin?tab=ai-agents&section=connections");
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    const background = await page.locator(".ai-connection-card").evaluate(node => getComputedStyle(node).backgroundColor);
    if (theme === "light") expect(background).toBe("rgb(255, 255, 255)");
    await page.route("**/api/git-connections", route => route.fulfill({ json: [{ id: 1, name: "Team GitLab", account: "reader", provider: "gitlab", base_url: "https://git.example.test", enabled: true, status: "CONNECTED" }] }));
    await page.route("**/api/ticket-connectors", route => route.fulfill({ json: [{ id: 1, name: "Team Jira", platform: "jira", base_url: "https://jira.example.test", enabled: true, status: "CONNECTED", projects: [], environment_ids: [] }] }));
    for (const [url, selector, controls] of [
      ["/admin?tab=environments&sources=git", ".git-connection-card", "[data-git-actions]"],
      ["/admin?tab=connectors", ".publication-connection-card", "[data-publication-actions]"],
    ]) {
      await page.goto(url);
      const card = page.locator(selector);
      await expect(card).toBeVisible();
      expect(await card.evaluate(node => getComputedStyle(node).backgroundColor)).toBe(background);
      const actions = card.locator(controls), box = (await card.boundingBox())!, actionBox = (await actions.boundingBox())!;
      const inset = await card.evaluate(node => Number.parseFloat(getComputedStyle(node).paddingRight) + Number.parseFloat(getComputedStyle(node).borderRightWidth));
      expect(Math.abs(box.x + box.width - inset - actionBox.x - actionBox.width)).toBeLessThan(2);
      expect(actionBox.y - box.y).toBeLessThan(110);
      await expect(actions.getByRole("button")).toHaveText([t("Edit")]);
      await expect(actions.locator("summary")).toHaveCount(1);
      await actions.locator("summary").click();
      const menu = actions.locator(".action-menu-items");
      await expect(menu.getByRole("button")).toHaveCount(3);
      for (const button of await menu.getByRole("button").all()) await expect(button.locator("svg")).toHaveCount(1);
      await actions.locator("summary").press("Escape");
      await expect(menu).not.toBeVisible();
      if (language === "fr") await page.screenshot({ path: `../.local/inline-ui/${test.info().project.name}-${selector.slice(1)}.png` });
    }
  });

  test(`content and activity scroll independently while navigation stays fixed in ${language}`, async ({ page }) => {
    await setup(page, language);
    await page.route("**/api/library/skill", route => route.fulfill({ json: Array.from({ length: 25 }, (_, index) => ({ slug: `skill-${index}`, name: `Skill ${index}`, objective: "A reusable procedure", enabled: false, version: 1, compatibility: [], instructions: "Consult the sources", skills: [] })) }));
    await page.route("**/api/queue", route => route.fulfill({ json: Array.from({ length: 25 }, (_, index) => ({ id: index + 1, kind: "analysis", status: "RUNNING", request_status: "ANALYZING", title: `Working analysis ${index}`, environment_name: "Staging", operation: "Analyze", agent: "codex", queue_position: null, created_at: "2026-10-30T10:00:00Z", started_at: "2026-10-30T10:00:00Z", finished_at: null, error: "", href: `/analyses/item-${index}` })) }));
    await page.goto("/admin?tab=ai-agents&section=skills");
    const center = page.locator(".dashboard-center");
    const sidebar = page.getByRole("complementary", { name: t("Instance navigation"), exact: true });
    await expect(page.getByRole("article", { name: "Skill 24", exact: true })).toBeAttached();
    const before = (await sidebar.boundingBox())!;
    await center.hover();
    await page.mouse.wheel(0, 600);
    await expect.poll(() => center.evaluate(node => node.scrollTop)).toBeGreaterThan(250);
    expect((await sidebar.boundingBox())!.y).toBe(before.y);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await page.getByRole("button", { name: t("Activity"), exact: true }).click();
    const panel = page.viewportSize()!.width < 1280
      ? page.getByRole("dialog", { name: t("Activity"), exact: true })
      : page.locator("#desktop-task-queue");
    await expect(panel).toBeVisible();
    await expect(panel.locator(".queue-card")).toHaveCount(25);
    const contentTop = await center.evaluate(node => node.scrollTop);
    await panel.hover();
    await page.mouse.wheel(0, 600);
    await expect.poll(() => panel.evaluate(node => node.scrollTop)).toBeGreaterThan(250);
    expect(await center.evaluate(node => node.scrollTop)).toBe(contentTop);
    await panel.evaluate(node => { node.scrollTop = node.scrollHeight; });
    await page.mouse.wheel(0, 600);
    await expect.poll(() => center.evaluate(node => node.scrollTop)).toBe(contentTop);
    expect((await sidebar.boundingBox())!.y).toBe(before.y);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });
}
