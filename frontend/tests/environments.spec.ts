import { expect, test } from "./fixtures";

test("environment: changes, conflict and confirmed deletion", async ({
  page,
}) => {
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
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Environment name", { exact: true })
    .fill("Renamed validation");
  await dialog
    .getByRole("button", { name: "Review changes", exact: true })
    .click();
  await expect(
    dialog.getByText("Name: Interface validation → Renamed validation", {
      exact: true,
    }),
  ).toBeVisible();
  expect(writes).toBe(0);
  await dialog.getByRole("button", { name: "Confirm changes" }).click();
  await expect(dialog.getByRole("alert")).toContainText("has changed");
  await dialog.getByRole("button", { name: "Confirm changes" }).click();
  await expect(dialog).not.toBeVisible();
  await page
    .getByRole("button", { name: "Delete Renamed validation", exact: true })
    .click();
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
