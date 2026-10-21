import { test as base } from "@playwright/test";
export { expect } from "@playwright/test";

export const test = base.extend({
  page: async ({ page }, use) => {
    let settings = {
      name: "SpecHelper",
      primary_color: "#2563eb",
      short_label: "",
      allow_confrontation: true,
      language: "en",
    };
    await page.route("**/api/settings", async (route) => {
      if (route.request().method() === "PUT")
        settings = { ...settings, ...route.request().postDataJSON() };
      await route.fulfill({ json: settings });
    });
    await use(page);
  },
});
