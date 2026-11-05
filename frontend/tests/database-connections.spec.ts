import { test, expect } from "./fixtures";
import { translate } from "../src/lib/i18n";

for (const language of ["en", "fr"] as const) for (const theme of ["light", "dark"] as const) {
  const t = (key: string, parameters: Record<string, string | number> = {}) => translate(key, language, parameters);
  test(`PostgreSQL cards, inline edits and real actions in ${language} ${theme}`, async ({ page }, info) => {
    let databases = [
      { id: 1, name: "Business reader", status: "CONNECTED", host: "host.docker.internal", port: 5432, database: "business", username: "readonly", sslmode: "require", checked_at: "2026-11-02T05:31:03Z" as string | null },
      { id: 2, name: "Direct PostgreSQL", status: "ERROR", host: "db.local", port: 5433, database: "direct", username: "reader", sslmode: "disable", checked_at: null },
    ];
    const writes: { method: string; id?: number; body?: Record<string, unknown> }[] = [];
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname.slice(4), method = route.request().method();
      let json: unknown = [];
      if (path === "/access/session") json = { authenticated: true, mode: "local" };
      if (path === "/settings") json = { name: "SpecHelper", language };
      if (path === "/connections") json = { ais: [], databases };
      if (path === "/orchestration-settings") json = { reliability_protocol: "2.4" };
      const match = path.match(/^\/connections\/databases\/(\d+)(\/test)?$/);
      if (match) {
        const id = Number(match[1]);
        writes.push({ method, id, body: method === "PUT" ? route.request().postDataJSON() : undefined });
        if (method === "PUT") {
          const body = route.request().postDataJSON();
          databases = databases.map(database => database.id === id ? { ...database, name: body.name, host: body.host } : database);
        }
        if (match[2]) databases = databases.map(database => database.id === id ? { ...database, status: "CONNECTED", checked_at: "2026-11-02T05:32:03Z" } : database);
        if (method === "DELETE") {
          if (id === 1) return route.fulfill({ status: 409, json: { detail: "This PostgreSQL connection is used by an environment or analysis history." } });
          databases = databases.filter(database => database.id !== id);
        }
        return route.fulfill({ json: { id, status: "CONNECTED", checks: { connection: true, read: true, read_only: true } } });
      }
      if (path === "/connections/databases" && method === "POST") {
        const body = route.request().postDataJSON(); writes.push({ method, body });
        databases.push({ id: 3, name: body.name, status: "CONNECTED", host: "new-db.example", port: 5432, database: "new", username: "reader", sslmode: "require", checked_at: "2026-11-02T05:32:03Z" });
        return route.fulfill({ status: 201, json: { id: 3, status: "CONNECTED", checks: { connection: true, read: true, read_only: true } } });
      }
      return route.fulfill({ json });
    });
    await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), theme);
    await page.goto("/admin?tab=environments&sources=postgres");
    const section = page.getByRole("region", { name: t("PostgreSQL connections"), exact: true });
    const first = section.getByRole("region", { name: "Business reader", exact: true });
    const second = section.getByRole("region", { name: "Direct PostgreSQL", exact: true });
    await expect(first.locator(".badge")).toHaveText(t("Connected"));
    await expect(first).toContainText(`${new URL(page.url()).hostname}:5432`);
    await expect(first).not.toContainText('host.docker.internal');
    await expect(second.locator(".badge")).toHaveText(t("Connection failed"));
    const dateLocale = language === "fr" ? "fr-FR" : "en-US";
    const dateText = await page.evaluate(({ date, dateLocale }) => new Date(date).toLocaleString(dateLocale), { date: "2026-11-02T05:31:03Z", dateLocale });
    await expect(first).toContainText(t("Last checked") + ": " + dateText);
    await expect(second).toContainText(t("Last checked") + ": " + t("Verification date not recorded"));
    for (const card of [first, second]) {
      const logo = card.locator('img[data-provider="postgresql"]');
      await expect(logo).toHaveAttribute("src", "/postgresql.png");
      await expect.poll(() => logo.evaluate((node: HTMLImageElement) => node.complete && node.naturalWidth > 0)).toBe(true);
      const edit = card.getByRole("button", { name: t("Edit"), exact: true });
      await expect(edit.locator("svg")).toHaveCount(1);
      const header = await card.locator("[data-database-actions]").boundingBox(), box = await card.boundingBox();
      expect(Math.abs(box!.x + box!.width - header!.x - header!.width - 17)).toBeLessThan(2);
    }
    await first.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(first.locator("form")).toBeVisible();
    await expect(first.getByLabel(t('Host'),{exact:true})).toHaveValue(new URL(page.url()).hostname);
    await expect(second.locator("form")).toHaveCount(0);
    await expect(first.getByLabel(t("PostgreSQL username"), { exact: true })).toHaveValue("readonly");
    await expect(first.getByLabel(t("Password"), { exact: true })).toHaveValue("");
    await expect(first.getByLabel(t("Password"), { exact: true })).not.toHaveAttribute("required", "");
    await expect(first.locator("[data-editor-actions]").getByRole("button")).toHaveText([t("Cancel"), t("Save")]);
    await first.getByLabel(t("Connection name"), { exact: true }).fill("Unsaved edit");
    await first.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(first.locator("form")).toHaveCount(0);
    expect(writes).toEqual([]);
    await first.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(first.getByLabel(t("Connection name"), { exact: true })).toHaveValue("Business reader");
    await first.getByLabel(t("Host"), { exact: true }).fill("saved-db.example");
    await first.getByRole("button", { name: t("Save"), exact: true }).click();
    await expect(first.locator("form")).toHaveCount(0);
    expect(writes[0]).toMatchObject({ method: "PUT", id: 1, body: { host: "saved-db.example", password: "" } });
    await expect(first).toContainText("saved-db.example:5432");
    await second.getByLabel(t("More actions for {name}", { name: "Direct PostgreSQL" }), { exact: true }).click();
    await expect(second.locator(".action-menu-items button svg")).toHaveCount(2);
    await second.getByRole("button", { name: t("Test connection"), exact: true }).click();
    await expect(second.locator(".badge")).toHaveText(t("Connected"));
    await expect(second).not.toContainText(t("Verification date not recorded"));
    await first.getByLabel(t("More actions for {name}", { name: "Business reader" }), { exact: true }).click();
    await first.getByRole("button", { name: t("Delete"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Delete PostgreSQL connection"), exact: true });
    await dialog.getByRole("button", { name: t("Confirm deletion"), exact: true }).click();
    await expect(dialog.getByRole("alert")).toHaveText(t("This PostgreSQL connection is used by an environment or analysis history."));
    await dialog.getByRole("button", { name: t("Cancel"), exact: true }).click();
    await expect(first).toBeVisible();
    await second.getByLabel(t("More actions for {name}", { name: "Direct PostgreSQL" }), { exact: true }).click();
    await second.getByRole("button", { name: t("Delete"), exact: true }).click();
    await dialog.getByRole("button", { name: t("Confirm deletion"), exact: true }).click();
    await expect(second).toHaveCount(0);
    await section.getByRole("button", { name: t("Add connection"), exact: true }).click();
    const create = section.locator("form");
    await create.getByLabel(t("Connection name"), { exact: true }).fill("New direct reader");
    await create.getByLabel(t("Use a PostgreSQL URL"), { exact: true }).check();
    await create.getByLabel(t("PostgreSQL URL"), { exact: true }).fill("postgresql://reader:fixture-password@new-db.example/new");
    await create.getByRole("button", { name: t("Save"), exact: true }).click();
    await expect(section.getByRole("region", { name: "New direct reader", exact: true })).toBeVisible();
    expect(writes.map(write => write.method)).toEqual(["PUT", "POST", "DELETE", "DELETE", "POST"]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await section.screenshot({ path: "../.local/postgresql-ui/" + language + "-" + theme + "-" + info.project.name + ".png" });
  });
}
