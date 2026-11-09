import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";

const current = { id: "1", remote_id: "1", path: "team/current", default_branch: "main", is_fork: false };
const needle = { id: "77", remote_id: "77", path: "team/needle", default_branch: "main", is_fork: false };

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
});

async function setup(page: any, language: "en" | "fr") {
  await page.route("**/api/access/session", (route: any) => route.fulfill({ json: { mode: "local", authenticated: true } }));
  await page.route("**/api/settings", (route: any) => route.fulfill({ json: { name: "SpecHelper", language } }));
  await page.route("**/api/connections", (route: any) => route.fulfill({ json: { ais: [], databases: [], github: { status: "DISCONNECTED" } } }));
  await page.route("**/api/git-connections", (route: any) => route.fulfill({ json: [{ id: 9, name: "Source", provider: "github", enabled: true, status: "CONNECTED" }] }));
  await page.goto("/admin?tab=environments");
  await page.getByRole("button", { name: translate("New environment", language), exact: true }).click();
  await page.locator("#new-source-0-connection").selectOption("9");
}

for (const language of ["en", "fr"] as const) {
  test(`large repository and tag searches follow actual remote continuations in ${language}`, async ({ page }) => {
    const t = (key: string) => translate(key, language);
    const pages: number[] = [];
    await page.route("**/api/git-connections/9/projects?**", route => {
      const q = new URL(route.request().url()).searchParams;
      const pageNumber = Number(q.get("page"));
      if (q.get("search") !== "needle") return route.fulfill({ json: { items: [current], has_more: false } });
      pages.push(pageNumber);
      return route.fulfill({ json: pageNumber === 1 ? { items: [], page: 5, has_more: true, next_page: 6 } : { items: [needle], page: 7, has_more: false } });
    });
    const tagPages: number[] = [];
    await page.route("**/api/git-connections/9/branches?**", route => {
      const q = new URL(route.request().url()).searchParams;
      if (q.get("kind") !== "tag") return route.fulfill({ json: { items: [{ name: "main" }], has_more: false } });
      const pageNumber = Number(q.get("page"));
      tagPages.push(pageNumber);
      return route.fulfill({ json: pageNumber === 1 ? { items: [], page: 5, has_more: true, next_page: 6 } : { items: [{ name: "release/v9", ref: "tag:release/v9", kind: "tag" }], page: 6, has_more: false } });
    });
    await setup(page, language);
    await page.locator("#new-source-0-search").fill(" needle ");
    const projects = page.locator("#new-source-0-repository");
    await expect(projects.locator('option[value="77"]')).toHaveText("team/needle");
    expect(pages).toEqual([1, 6]);
    await projects.selectOption("77");
    await page.locator("#new-source-0-ref-kind").selectOption("tag");
    await expect(page.locator("#new-source-0-branch-search")).toHaveAccessibleName(t("Search tags"));
    const refs = page.locator("#new-source-0-branch");
    await expect(refs.locator('option[value="tag:release/v9"]')).toHaveText("release/v9");
    expect(tagPages).toEqual([1, 6]);
    await refs.selectOption("tag:release/v9");
    await expect(refs).toHaveValue("tag:release/v9");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`superseded searches never replace results or the selected repository in ${language}`, async ({ page }) => {
    let releaseOld: (() => void) | undefined;
    let oldStarted = false;
    let oldFinished = false;
    const oldGate = new Promise<void>(resolve => { releaseOld = resolve; });
    await page.route("**/api/git-connections/9/projects?**", async route => {
      const search = new URL(route.request().url()).searchParams.get("search");
      if (search === "old") {
        oldStarted = true;
        await oldGate;
        await route.fulfill({ status: 422, json: { detail: "Obsolete search error" } }).catch(() => {});
        oldFinished = true;
        return;
      }
      await route.fulfill({ json: { items: search === "needle" ? [needle] : [current], has_more: false } });
    });
    await page.route("**/api/git-connections/9/branches?**", route => route.fulfill({ json: { items: [{ name: "main" }], has_more: false } }));
    await setup(page, language);
    const projects = page.locator("#new-source-0-repository");
    await expect(projects.locator('option[value="1"]')).toBeAttached();
    await projects.selectOption("1");
    const search = page.locator("#new-source-0-search");
    await search.fill("old");
    await expect.poll(() => oldStarted).toBe(true);
    const aborted = page.waitForEvent("requestfailed", { predicate: request => new URL(request.url()).searchParams.get("search") === "old" });
    await search.fill("needle");
    await aborted;
    await expect(projects.locator('option[value="77"]')).toBeAttached();
    releaseOld!();
    await expect.poll(() => oldFinished).toBe(true);
    await expect(projects).toHaveValue("1");
    await expect(projects.locator('option[value="1"]')).toContainText(translate("Selected", language));
    await expect(page.getByRole("alert").filter({ hasText: "Obsolete search error" })).toHaveCount(0);
  });
}
