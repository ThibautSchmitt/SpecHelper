import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";

for (const language of ["en", "fr"] as const) {
  test(`Git server URLs can be entered and edited with explicit provider limits in ${language}`, async ({ page }) => {
    const t = (key: string) => translate(key, language);
    let saved: any = { id: 9, name: "Internal source", provider: "gitlab", base_url: "https://old.example.test", account: "reader", enabled: true, status: "CONNECTED", has_secret: true, referenced_environments: 0 };
    const changes: any[] = [];
    await page.route("**/api/**", route => route.fulfill({ json: [] }));
    await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true } }));
    await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language } }));
    await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [], github: { status: "DISCONNECTED" } } }));
    await page.route("**/api/git-connections", route => {
      if (route.request().method() === "POST") { changes.push(route.request().postDataJSON()); return route.fulfill({ json: saved }); }
      return route.fulfill({ json: [saved] });
    });
    await page.route("**/api/git-connections/9", route => {
      const payload = route.request().postDataJSON(); changes.push(payload); saved = { ...saved, ...payload };
      return route.fulfill({ json: saved });
    });
    await page.goto("/admin?tab=environments");
    await page.getByRole("button", { name: t("Manage Git connections"), exact: true }).click();
    const source = page.getByRole("region", { name: "reader", exact: true });
    await source.getByRole("button", { name: t("Edit"), exact: true }).click();
    const url = page.locator("#git-source-server");
    await expect(url).toBeEditable();
    await url.fill("https://new.example.test/gitlab");
    const token = page.locator("#git-source-secret");
    await expect(token).toHaveValue("");
    await expect(token).toHaveAttribute("required", "");
    await token.fill("synthetic-read-only-token");
    await page.getByRole("button", { name: t("Save connection"), exact: true }).click();
    expect(changes[0]).toMatchObject({ base_url: "https://new.example.test/gitlab", secret: "synthetic-read-only-token" });
    await source.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(url).toHaveValue("https://new.example.test/gitlab");
    await page.getByRole("button", { name: t("Cancel"), exact: true }).click();
    await page.getByRole("button", { name: t("New Git connection"), exact: true }).click();
    await expect(url).toHaveJSProperty("readOnly", true);
    await expect(page.locator("#git-source-server-help")).toContainText("github.com");
    await page.locator("#git-source-provider").selectOption("gitlab");
    await expect(url).toBeEditable();
    await url.fill("https://another.example.test");
    await page.locator("#git-source-name").fill("Another source");
    await token.fill("synthetic-other-token");
    await page.getByRole("button", { name: t("Add Git connection"), exact: true }).click();
    expect(changes[1]).toMatchObject({ provider: "gitlab", base_url: "https://another.example.test" });
  });
}
