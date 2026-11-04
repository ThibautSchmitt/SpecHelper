import { expect, test } from "./fixtures";
import fr from "../src/locales/fr.json";
import en from "../src/locales/en.json";

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => ((language === "fr" ? fr : en) as Record<string, string>)[key] || key;
  test(`remote branch status and targeted update in ${language}`, async ({ page }, info) => {
    await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "fr" ? "dark" : "light");
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language } }));
    await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [], github: { status: "DISCONNECTED" } } }));
    await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4" } }));
    let environment = {
      id: 1, name: "Staging", revision: 4, status: "READY", error: "", database_id: null, database_name: null,
      git_sync_status: "PARTIAL", git_check_running: false,
      repositories: [
        { id: 11, repository: "team/api", branch: "main", sha: "a".repeat(40), last_checked_at:"2026-11-04T06:00:00Z", synced_at:"2026-11-03T05:00:00Z", git_status: { status: "BEHIND", behind: 1 } },
        { id: 12, repository: "team/web", branch: "release/2026.11/long-branch", sha: "b".repeat(40), git_status: { status: "CURRENT", behind: 0 } },
      ],
    };
    await page.route("**/api/environments", route => route.fulfill({ json: [environment] }));
    const writes: { url: string; payload: unknown }[] = [];
    const checks: unknown[] = [];
    await page.route("**/api/environments/1/check-updates", route => {
      checks.push(route.request().postDataJSON());
      environment = {...environment,git_check_running:true};
      return route.fulfill({json:{status:"QUEUED"}});
    });
    await page.route("**/api/environments/1/repositories/*/sync", route => {
      writes.push({ url: new URL(route.request().url()).pathname, payload: route.request().postDataJSON() });
      environment = { ...environment, status: "PENDING" };
      return route.fulfill({ json: { status: "QUEUED" } });
    });
    await page.goto("/admin?tab=environments");
    const card = page.locator(".environment-card");
    const tag = card.locator(".title-tags .badge");
    await expect(tag).toHaveText(t("Partially up to date"));
    await expect(tag).toHaveAttribute("data-state", "PARTIAL");
    await expect(tag).toHaveCSS("color", language === "fr" ? "rgb(250, 204, 21)" : "rgb(133, 77, 14)");
    const rows = card.getByRole("row");
    const behindBadge=rows.filter({hasText:'team/api'}).locator('[data-repository-freshness-badge]');
    const currentBadge=rows.filter({hasText:'team/web'}).locator('[data-repository-freshness-badge]');
    await expect(behindBadge).toHaveText(t('Behind'));
    await expect(behindBadge).toHaveAttribute('data-state','PARTIAL');
    await expect(behindBadge).toHaveCSS('color',await tag.evaluate(node=>getComputedStyle(node).color));
    await expect(behindBadge).toHaveCSS('background-color',await tag.evaluate(node=>getComputedStyle(node).backgroundColor));
    await expect(currentBadge).toHaveText(t('Up to date'));
    await expect(currentBadge).toHaveAttribute('data-state','READY');
    await expect(rows.filter({hasText:'team/web'}).locator('[data-branch-update-row]')).toHaveCount(0);
    await expect(card.getByRole("columnheader",{name:t("Code freshness"),exact:true})).toHaveCount(0);
    await expect(card.getByRole("columnheader",{name:"SHA",exact:true})).toHaveCount(0);
    const localVersion=rows.filter({hasText:"team/api"}).locator(".repository-version");
    await expect(localVersion.locator("code")).toBeVisible();
    const table=card.locator('[data-environment-git-table]');
    const tableBox=await table.boundingBox();
    const branchHeader=await table.getByRole('columnheader',{name:t('Branch / tag'),exact:true}).boundingBox();
    expect(Math.abs(branchHeader!.x-(tableBox!.x+tableBox!.width/2))).toBeLessThan(1);
    const branchBox=await rows.filter({hasText:'team/api'}).locator('[data-repository-branch]').boundingBox();
    const shaBox=await localVersion.boundingBox();
    expect(shaBox!.y).toBeGreaterThanOrEqual(branchBox!.y+branchBox!.height);
    await expect(localVersion.locator("summary")).toHaveCount(0);
    await card.screenshot({path:`../.local/git-freshness-${language}-${info.project.name}.png`});
    await expect(localVersion.locator("code")).toHaveText("a".repeat(10));
    await page.context().grantPermissions(["clipboard-read","clipboard-write"]);
    await localVersion.getByRole("button",{name:t("Copy full local commit"),exact:true}).click();
    await expect.poll(()=>page.evaluate(()=>navigator.clipboard.readText())).toBe("a".repeat(40));
    for(const label of ["Local version details","Local commit","Last successful remote check","Last local update"])
      await expect(localVersion).not.toContainText(t(label));
    await expect(rows.filter({ hasText: "team/api" })).toContainText(t("1 commit behind"));
    await expect(rows.filter({ hasText: "team/web" })).toContainText(t("Up to date"));
    await expect(card.getByRole("button", { name: /team\/web/ })).toHaveCount(0);
    await card.getByRole("button", { name: t("Update {repository} · {branch}").replace("{repository}", "team/api").replace("{branch}", "main"), exact: true }).click();
    await expect(tag).toHaveText(t("Update scheduled"));
    await expect(page.getByText(t('Update scheduled.'),{exact:true})).toHaveCount(0);
    await expect(card.getByRole("button", { name: /team\/api/ })).toBeDisabled();
    expect(writes).toEqual([{ url: "/api/environments/1/repositories/11/sync", payload: { expected_revision: 4 } }]);
    environment = { ...environment, status: "READY", git_sync_status: "SYNCED", repositories: environment.repositories.map(repo => ({ ...repo, git_status: { status: "CURRENT", behind: 0 } })) };
    await expect(tag).toHaveText(t("Up to date"), { timeout: 10000 });
    const success = await tag.evaluate(element => {
      const probe = document.createElement("span");
      probe.style.color = "var(--success)";
      probe.style.backgroundColor = "var(--success-soft)";
      element.append(probe);
      const result = { color: getComputedStyle(probe).color, background: getComputedStyle(probe).backgroundColor };
      probe.remove();
      return result;
    });
    await expect(tag).toHaveCSS("color", success.color);
    await expect(tag).toHaveCSS("background-color", success.background);
    await expect(currentBadge).toHaveCSS('color',success.color);
    await expect(currentBadge).toHaveCSS('background-color',success.background);
    await expect(card.getByRole("button", { name: /team\/api/ })).toHaveCount(0);
    environment = { ...environment, git_sync_status: "OUTDATED", repositories: environment.repositories.map(repo => ({ ...repo, git_status: { status: "BEHIND", behind: 3 } })) };
    await expect(tag).toHaveText(t("Update needed"), { timeout: 10000 });
    const danger = await tag.evaluate(element => {
      const probe = document.createElement("span");
      probe.style.color = "var(--danger)";
      element.append(probe);
      const color = getComputedStyle(probe).color;
      probe.remove();
      return color;
    });
    await expect(tag).toHaveCSS("color", danger);
    await expect(rows.filter({ hasText: "team/api" })).toContainText(t("{count} commits behind").replace("{count}", "3"));
    const repositoryRow=rows.filter({hasText:"team/api"});
    const version=repositoryRow.locator('[data-local-version-row]');
    const freshness=repositoryRow.locator('[data-branch-update-row]');
    const versionBox=await version.boundingBox();
    const freshnessBox=await freshness.boundingBox();
    expect(freshnessBox!.y).toBeGreaterThanOrEqual(versionBox!.y+versionBox!.height);
    await expect(freshness.getByRole('button')).toContainText(t('Update source'));
    await expect(freshness.getByRole('button')).toHaveClass(/underline/);
    await expect(page.locator("body")).not.toContainText(/synchronis|synchroniz/i);
    environment = { ...environment, git_sync_status: "UNKNOWN", repositories: environment.repositories.map(repo => ({ ...repo, git_status: { status: "MISSING", behind: 0 } })) };
    await expect(tag).toHaveText(t("Branch status not verified"), { timeout: 10000 });
    await expect(rows.filter({ hasText: "team/api" })).toContainText(t("Remote branch not found"));
    await expect(card.getByRole("button", { name: /team\/api/ })).toHaveCount(0);
    expect(writes).toHaveLength(1);
    environment = {...environment,repositories:environment.repositories.map(repo=>({...repo,git_status:{status:"UNAVAILABLE",behind:0}}))};
    await expect(rows.filter({hasText:"team/api"})).toContainText(t("Unknown state"),{timeout:10000});
    await expect(card.locator('[data-repository-freshness-badge]')).toHaveCount(0);
    await card.getByLabel(t("More actions for {name}").replace("{name}","Staging"),{exact:true}).click();
    await card.getByRole("button",{name:t("Check for updates"),exact:true}).click();
    await expect.poll(()=>checks.length).toBe(1);
    expect(checks).toEqual([{expected_revision:4}]);
    expect(writes).toHaveLength(1);
    await expect(rows.filter({hasText:"team/api"})).toContainText(t("Unknown state"));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
