import { test, expect } from "./fixtures";

test("late settings reads cannot overwrite a saved instance identity", async ({
  page,
}) => {
  let settings = {
    name: "SpecHelper",
    primary_color: "#2563eb",
    short_label: "",
    language: "en",
    allow_confrontation: true,
  };
  let holdNext = false;
  let release = () => {};
  let observed = () => {};
  let completed = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const captured = new Promise<void>((resolve) => {
    observed = resolve;
  });
  const fulfilled = new Promise<void>((resolve) => {
    completed = resolve;
  });
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() === "PUT") {
      settings = { ...settings, ...route.request().postDataJSON() };
    } else if (holdNext) {
      holdNext = false;
      const previous = { ...settings };
      observed();
      await gate;
      await route.fulfill({ json: previous });
      completed();
      return;
    }
    await route.fulfill({ json: settings });
  });
  await page.route("**/api/connections", (route) =>
    route.fulfill({
      json: { github: { status: "DISCONNECTED" }, ais: [], databases: [] },
    }),
  );
  await page.route("**/api/environments", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/system", (route) =>
    route.fulfill({
      json: {
        jobs: [],
        runtime: "",
        usage: "UNKNOWN",
        max_analysis_seconds: 300,
      },
    }),
  );
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/queue", (route) => route.fulfill({ json: [] }));
  try {
    await page.goto("/admin");
    await page.getByRole("button", { name: "Appearance", exact: true }).click();
    await expect(
      page.getByLabel("Instance name", { exact: true }),
    ).toBeEnabled();
    holdNext = true;
    await page.evaluate(() =>
      window.dispatchEvent(new Event("settings-updated")),
    );
    await captured;
    await page
      .getByLabel("Instance name", { exact: true })
      .fill("Saved team identity");
    await page.getByLabel("Primary color", { exact: true }).fill("#7c3aed");
    await page
      .getByRole("button", { name: "Save settings", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("saved");
    await expect(
      page.getByRole("link", { name: "Saved team identity", exact: true }),
    ).toBeVisible();
    release();
    await fulfilled;
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    await expect(page.getByLabel("Instance name", { exact: true })).toHaveValue(
      "Saved team identity",
    );
    await expect(
      page.getByRole("link", { name: "Saved team identity", exact: true }),
    ).toBeVisible();
  } finally {
    release();
  }
});
