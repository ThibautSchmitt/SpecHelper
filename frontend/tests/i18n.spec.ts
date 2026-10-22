import { test, expect } from "./fixtures";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";
import { translate } from "../src/lib/i18n";

test("system notices translate in both directions without rewriting user text", () => {
  expect(translate("Result v12 available.", "fr")).toBe(
    fr["Result v{number} available."].replace("{number}", "12"),
  );
  expect(
    translate(
      fr["Result v{number} available."].replace("{number}", "12"),
      "en",
    ),
  ).toBe("Result v12 available.");
  expect(translate("Unexpected repository error: custom detail", "fr")).toBe(
    "Unexpected repository error: custom detail",
  );
  expect(translate("Result v{number} available.", "fr", { number: 3 })).toBe(
    fr["Result v{number} available."].replace("{number}", "3"),
  );
});

test("English and French catalogs have matching keys and placeholders", () => {
  expect(Object.keys(en).sort()).toEqual(Object.keys(fr).sort());
  for (const key of Object.keys(en) as (keyof typeof en)[]) {
    expect(en[key]).toBe(key);
    expect(fr[key].trim().length).toBeGreaterThan(0);
    const placeholders = (text: string) =>
      [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
    expect(placeholders(fr[key]), key).toEqual(placeholders(en[key]));
  }
});

test("admin language persists across navigation, reload and translated errors", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/requests", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/connections", (route) =>
    route.fulfill({
      json: {
        github: { status: "DISCONNECTED", account: "" },
        databases: [],
        ais: [
          {
            id: 1,
            agent: "codex",
            status: "CONNECTED",
            availability: "AVAILABLE",
            enabled: true,
            account: "ChatGPT",
          },
        ],
      },
    }),
  );
  await page.route("**/api/connections/ai/1/test", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "The assistant connection could not be verified." },
    }),
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "Instance", exact: true }).click();
  await expect(
    page.getByLabel("Application language", { exact: true }),
  ).toHaveValue("en");
  await page
    .getByLabel("Application language", { exact: true })
    .selectOption("fr");
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByRole("status")).toContainText(
    fr["Instance settings saved."],
  );
  await expect(
    page.getByLabel(fr["Application language"], { exact: true }),
  ).toHaveValue("fr");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `../.local/screenshots/i18n-fr-${info.project.name}.png`,
    fullPage: true,
  });
  await page.reload();
  await page
    .getByRole("button", { name: fr["Connections"], exact: true })
    .click();
  await page
    .getByRole("region", { name: "ChatGPT", exact: true })
    .getByRole("button", { name: fr["Test connection"], exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    fr["The assistant connection could not be verified."],
  );
  await page.getByRole("link", { name: fr["Requests"], exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: fr["From need to ticket, simply."],
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByLabel(fr["Describe your need"], { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: fr["Settings"], exact: true }).click();
  await page.getByRole("button", { name: "Instance", exact: true }).click();
  await page
    .getByLabel(fr["Application language"], { exact: true })
    .selectOption("en");
  await page
    .getByRole("button", { name: fr["Save settings"], exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(
    page.getByLabel("Application language", { exact: true }),
  ).toHaveValue("en");
  await expect(
    page.getByText("Advanced analysis options", { exact: true }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `../.local/screenshots/i18n-en-${info.project.name}.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
