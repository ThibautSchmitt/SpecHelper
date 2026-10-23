import { test as base } from "@playwright/test";
export { expect } from "@playwright/test";

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.route("**/api/access/session", (route) => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
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
    await page.route("**/api/git-connections", (route) =>
      route.request().method() === "GET"
        ? route.fulfill({
            json: [
              {
                id: 1,
                name: "Team GitHub",
                provider: "github",
                base_url: "https://github.com",
                enabled: true,
                status: "CONNECTED",
                account: "team",
                referenced_environments: 0,
              },
            ],
          })
        : route.fallback(),
    );
    await page.route("**/api/ai-connections", (route) =>
      route.request().method() === "GET"
        ? route.fulfill({
            json: [
              {
                id: 1,
                name: "ChatGPT",
                agent: "codex",
                identity_id: "codex",
                enabled: true,
                status: "CONNECTED",
                availability: "AVAILABLE",
                model: "",
                account: "",
                quota_windows: {},
              },
              {
                id: 2,
                name: "Claude",
                agent: "claude",
                identity_id: "claude",
                enabled: true,
                status: "CONNECTED",
                availability: "AVAILABLE",
                model: "",
                account: "",
                quota_windows: {},
              },
            ],
          })
        : route.fallback(),
    );
    await use(page);
  },
});
