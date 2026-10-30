import { expect, test } from "./fixtures";

test("environment: changes, conflict and confirmed deletion", async ({
  page,
}) => {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language: "en" } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { ais: [], databases: [], github: { status: "DISCONNECTED" } } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4" } }));
  let writes = 0;
  let stale = true;
  let environment = {
    id: 998,
    name: "Interface validation",
    revision: 1,
    status: "READY",
    error: "",
    database_id: null,
    database_name: null,
    repositories: [
      {
        id: 1,
        repository: "fixture/contracts",
        branch: "main",
        sha: "a".repeat(40),
      },
    ],
  };
  let deleted = false;
  await page.route("**/api/environments", (route) =>
    route.fulfill({ json: deleted ? [] : [environment] }),
  );
  await page.route("**/api/environments/998", async (route) => {
    const data = route.request().postDataJSON();
    writes++;
    if (route.request().method() === "PATCH") {
      expect(data.expected_revision).toBe(1);
      if (stale) {
        stale = false;
        return route.fulfill({
          status: 409,
          json: { detail: "The environment has changed. Refresh the page." },
        });
      }
      environment = { ...environment, name: data.name, revision: 2 };
    } else {
      expect(route.request().method()).toBe("DELETE");
      expect(data).toEqual({
        confirm_name: "Renamed validation",
        expected_revision: 2,
      });
      deleted = true;
    }
    await route.fulfill({ json: environment });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  await page
    .getByRole("button", { name: "Edit Interface validation", exact: true })
    .click();
  const editor = page.getByRole("region", { name: "Edit environment", exact: true });
  await editor
    .getByLabel("Environment name", { exact: true })
    .fill("Renamed validation");
  expect(writes).toBe(0);
  await expect(editor.locator("[data-editor-actions]").getByRole("button")).toHaveText(["Cancel", "Save"]);
  await editor.getByRole("button", { name: "Save", exact: true }).click();
  await expect(editor.getByRole("alert")).toContainText("has changed");
  await expect(editor.getByLabel("Environment name", { exact: true })).toHaveValue("Renamed validation");
  await editor.getByRole("button", { name: "Save", exact: true }).click();
  await expect(editor).not.toBeVisible();
  await page
    .getByRole("button", { name: "Delete Renamed validation", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", {
    name: "Confirm deletion",
  });
  await expect(confirm).toBeDisabled();
  await dialog
    .getByLabel("Type the environment name to confirm")
    .fill("Renamed validation");
  await confirm.click();
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Renamed validation", exact: true }),
  ).not.toBeVisible();
  expect(writes).toBe(3);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
