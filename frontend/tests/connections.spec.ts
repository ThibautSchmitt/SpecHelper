import { test, expect } from "./fixtures";

test("GitHub: guided sign-in, temporary code and cancellation", async ({
  page,
}) => {
  const id = "11111111-1111-4111-8111-111111111111";
  const state = {
    id,
    provider: "github",
    status: "AWAITING_USER",
    verification_uri: "https://github.com/login/device",
    user_code: "ABCD-EFGH",
    input_required: false,
    message: "Complete sign-in on the website for GitHub.",
    expires_at: "2099-01-01T00:00:00Z",
  };
  let cancelled = false;
  await page.route("**/api/git-connections/1/auth/start", async (route) => {
    expect(route.request().method()).toBe("POST");
    await route.fulfill({ json: state });
  });
  await page.route(`**/api/connections/attempts/${id}**`, async (route) => {
    if (route.request().url().endsWith("/cancel")) cancelled = true;
    await route.fulfill({
      json: { ...state, status: cancelled ? "CANCELLED" : state.status },
    });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "AI & Agents", exact: true }).click();
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Connect with GitHub", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "AI & Agents", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Connect with ChatGPT", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Connect with Claude", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#github-token")).toHaveCount(0);
  await expect(
    page.getByText("docker compose exec", { exact: false }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  await page
    .getByRole("button", { name: "Connect with GitHub", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Sign in with GitHub" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("ABCD-EFGH", { exact: true })).toBeVisible();
  await expect(
    dialog.getByRole("link", { name: "Continue on GitHub" }),
  ).toHaveAttribute("href", "https://github.com/login/device");
  await dialog.getByRole("button", { name: "Copy code" }).click();
  await expect(dialog.getByRole("button", { name: "Copy code" })).toContainText(
    "Copied",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(cancelled).toBe(true);
});

test("ChatGPT: sign-in completes in the interface", async ({ page }) => {
  const id = "22222222-2222-4222-8222-222222222222";
  let complete = false;
  const state = {
    id,
    provider: "codex",
    status: "AWAITING_USER",
    verification_uri: "https://auth.openai.com/codex/device",
    user_code: "ABCDE-FGHIJ",
    input_required: false,
    message: "Complete sign-in on the website for ChatGPT.",
    expires_at: "2099-01-01T00:00:00Z",
  };
  await page.route("**/api/ai-connections/1/auth/start", async (route) => {
    expect(route.request().method()).toBe("POST");
    await route.fulfill({ json: state });
  });
  await page.route(`**/api/connections/attempts/${id}`, (route) =>
    route.fulfill({
      json: complete
        ? { ...state, status: "CONNECTED", message: "Connection successful." }
        : state,
    }),
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "AI & Agents", exact: true }).click();
  await page
    .getByRole("button", { name: "Connect with ChatGPT", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Sign in with ChatGPT",
  });
  await expect(
    dialog.getByRole("link", { name: "Continue on ChatGPT" }),
  ).toHaveAttribute("href", state.verification_uri);
  await expect(dialog.getByText("ABCDE-FGHIJ", { exact: true })).toBeVisible();
  complete = true;
  await expect(
    dialog.getByText("Connection successful.", { exact: true }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(dialog).not.toBeVisible();
});

test("Claude: enter the confirmation code without a terminal", async ({
  page,
}, testInfo) => {
  const id = "33333333-3333-4333-8333-333333333333";
  let complete = false;
  const state = {
    id,
    provider: "claude",
    status: "AWAITING_USER",
    verification_uri: "https://claude.com/cai/oauth/authorize?state=fixture",
    user_code: "",
    input_required: true,
    message: "Complete sign-in on the website for Claude.",
    expires_at: "2099-01-01T00:00:00Z",
  };
  await page.route("**/api/ai-connections/2/auth/start", async (route) => {
    expect(route.request().method()).toBe("POST");
    await route.fulfill({ json: state });
  });
  await page.route(`**/api/connections/attempts/${id}**`, async (route) => {
    if (route.request().url().endsWith("/code")) {
      expect(route.request().postDataJSON()).toEqual({
        code: "confirmation#fixture",
      });
      complete = true;
    }
    await route.fulfill({
      json: complete
        ? {
            ...state,
            input_required: false,
            status: "CONNECTED",
            message: "Connection successful.",
          }
        : state,
    });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "AI & Agents", exact: true }).click();
  await page
    .getByRole("button", { name: "Connect with Claude", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Sign in with Claude" });
  await expect(
    dialog.getByRole("link", { name: "Continue on Claude" }),
  ).toHaveAttribute("href", state.verification_uri);
  await dialog
    .getByLabel("Confirmation code", { exact: true })
    .fill("confirmation#fixture");
  await page.screenshot({
    path: `../.local/screenshots/claude-login-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await dialog
    .getByRole("button", { name: "Confirm connection", exact: true })
    .click();
  await expect(
    dialog.getByText("Connection successful.", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByLabel("Confirmation code", { exact: true }),
  ).toHaveCount(0);
});
