import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

type Language = "en" | "fr";
const text = (language: Language, key: string) => (language === "en" ? en : fr)[key as keyof typeof en] || key;
const model = {
  id: 31, agent: "antigravity", identifier: "fixture-gemini-model-exact", name: "Fixture Gemini",
  family: "google", source: "adapter", enabled: true, status: "SUPPORTED", checked_at: null, capabilities: { reasoning_efforts: [] },
};
const assistant = (changes = {}) => ({
  id: 3, name: "", agent: "antigravity", enabled: true, status: "CONNECTED",
  availability: "AVAILABLE", account: "", identity_id: "fixture-antigravity",
  roles: ["analyst", "counter_analyst", "verifier"], model: model.identifier,
  quota_status: { state: "unavailable", source: "antigravity_cli", reason: "not_reported", checked_at: new Date().toISOString() },
  quota_windows: {}, ...changes,
});
async function setup(page: Page, language: Language, values = [assistant()]) {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb", short_label: "" } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4", global_instructions: "State evidence limits.", allow_confrontation: true, verifier_enabled: true, allow_same_family_fallback: true, max_calls: 20, tool_timeout_seconds: 300 } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { ais: values, databases: [], github: { status: "DISCONNECTED" } } }));
  await page.route("**/api/ai-connections", route => route.fulfill({ json: values }));
  await page.route("**/api/ai-models?*", route => {
    const requested = new URL(route.request().url()).searchParams.get("agent");
    return route.fulfill({ json: { items: requested === "antigravity" ? [model] : [], discovery: { state: "supported", reason: "catalog_not_entitlement" } } });
  });
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "en" ? "light" : "dark");
}

for (const language of ["en", "fr"] as const) {
  const t = (key: string) => text(language, key);
  const openConnections = async (page: Page) => {
    await page.goto("/admin");
    await page.getByRole("button", { name: t("AI & Agents"), exact: true }).click();
  };

  test("native provider preserves discovered model and roles in " + language, async ({ page }) => {
    await setup(page, language, [assistant({ reasoning_effort: "high" })]);
    let edited: Record<string, unknown> | null = null;
    await page.route("**/api/ai-connections/3", route => { edited = route.request().postDataJSON(); return route.fulfill({ json: assistant({ ...edited }) }); });
    let saved: Record<string, unknown> | null = null;
    await page.route("**/api/ai-connections", route => {
      if (route.request().method() === "POST") saved = route.request().postDataJSON();
      return route.fulfill({ json: [assistant()] });
    });
    await openConnections(page);
    const card = page.locator("#ai-connection-3");
    await expect(card.locator(".connection-model-tag")).toHaveText(model.identifier);
    await card.getByRole("button", { name: t("Edit"), exact: true }).click();
    await expect(card.locator("#ai-config-provider")).toHaveCount(0);
    await expect(page.getByLabel(t("Reasoning"), { exact: true })).toHaveCount(0);
    await card.getByLabel(t("Connection name"), { exact: true }).fill("Existing Gemini");
    await page.getByRole("button", { name: t("Save connection"), exact: true }).click();
    await expect.poll(() => edited).toMatchObject({ model: model.identifier, reasoning_effort: "" });
    await expect(page.getByRole("navigation", { name: t("Administration"), exact: true }).getByRole("button")).toHaveCount(4);
    await page.getByRole("button", { name: t("New AI connection"), exact: true }).click();
    await page.getByLabel(t("Connection name"), { exact: true }).fill("Team Gemini");
    await page.getByLabel(t("Assistant"), { exact: true }).selectOption("antigravity");
    await page.getByLabel(t("Authentication identity"), { exact: true }).selectOption("3");
    await page.getByLabel(t("Model"), { exact: true }).selectOption(model.identifier);
    await expect(page.getByLabel(t("Reasoning"), { exact: true })).toHaveCount(0);
    await expect(page.getByLabel(t("Authentication identity"), { exact: true })).toHaveValue("3");
    await page.getByRole("button", { name: t("Add AI connection"), exact: true }).click();
    await expect.poll(() => saved).toMatchObject({
      name: "Team Gemini", agent: "antigravity", model: model.identifier, share_identity_from: 3,
      roles: ["analyst", "counter_analyst", "verifier"],
      reasoning_effort: "",
    });
    expect(saved).not.toHaveProperty("api_key");
    expect(saved).not.toHaveProperty("skill_overrides");
  });

  test("Google account authorization needs no API key in " + language, async ({ page }) => {
    await setup(page, language, [assistant({ status: "DISCONNECTED", availability: "UNKNOWN" })]);
    let started = 0;
    let keys = 0;
    let submitted: unknown = null;
    const attempt = {
      id: "fixture-google-login", provider: "antigravity", status: "AWAITING_USER",
      verification_uri: "https://accounts.google.com/o/oauth2/auth?state=fixture",
      user_code: "", input_required: true, message: "Complete sign-in on the website for Antigravity.",
    };
    await page.route("**/api/ai-connections/3/auth/start", route => {
      started += 1;
      return route.fulfill({ json: attempt });
    });
    await page.route("**/api/ai-connections/3/auth/api-key", route => { keys += 1; return route.fulfill({ status: 500 }); });
    await page.route("**/api/connections/attempts/fixture-google-login", route => route.fulfill({ json: attempt }));
    await page.route("**/api/connections/attempts/fixture-google-login/code", route => {
      submitted = route.request().postDataJSON();
      return route.fulfill({ json: { ...attempt, status: "CONNECTED", input_required: false, message: "Connection successful." } });
    });
    await openConnections(page);
    await page.getByRole("button", { name: t("Connect with") + " Antigravity", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Sign in with") + " Antigravity", exact: true });
    await expect(dialog).toContainText(t("Sign in with your Google account. Antigravity will verify whether your account can use the service. No API key is required."));
    await expect(dialog.getByRole("button", { name: t("Use a Gemini API key"), exact: true })).toBeVisible();
    expect(started).toBe(0);
    await dialog.getByRole("button", { name: t("Continue with Google"), exact: true }).click();
    await expect(dialog.getByRole("link", { name: t("Continue on") + " Antigravity" })).toHaveAttribute("href", attempt.verification_uri);
    await dialog.getByLabel(t("Confirmation code"), { exact: true }).fill("fixture-google-authorization-code");
    await dialog.getByRole("button", { name: t("Confirm connection"), exact: true }).click();
    await expect.poll(() => submitted).toEqual({ code: "fixture-google-authorization-code" });
    await expect(dialog).toContainText(t("Connection successful."));
    expect(started).toBe(1);
    expect(keys).toBe(0);
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("fixture-google-authorization-code");
  });

  test("Gemini key requires billing consent without verified-access claim in " + language, async ({ page }, info) => {
    await setup(page, language);
    let saved: Record<string, unknown> | null = null;
    const inference: string[] = [];
    page.on("request", request => { if (/\/(?:run|analyze)$/.test(request.url())) inference.push(request.url()); });
    await page.route("**/api/ai-connections/3/auth/api-key", route => {
      saved = route.request().postDataJSON();
      return route.fulfill({ json: { ...assistant(), authentication_mode: "api_key", access_verified: false } });
    });
    await openConnections(page);
    await page.locator("#ai-connection-3 .action-menu > summary").click();
    await page.getByRole("button", { name: t("Change account"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Sign in with") + " Antigravity", exact: true });
    await dialog.getByRole("button", { name: t("Use a Gemini API key"), exact: true }).click();
    await expect(dialog).toContainText(t("Gemini API use may be billed by Google. SpecHelper uses this key only for this explicitly configured identity; it never inherits a key from your environment."));
    const field = dialog.getByLabel(t("Gemini API key"), { exact: true });
    await expect(field).toHaveAttribute("type", "password");
    await expect(field).toBeFocused();
    await field.fill("fixture-key-not-a-live-secret");
    await expect(dialog.getByRole("button", { name: t("Save API credential"), exact: true })).toBeDisabled();
    expect(saved).toBeNull();
    await dialog.getByRole("checkbox", { name: t("I authorize use of this API key and accept any charges from my provider."), exact: true }).check();
    await dialog.getByRole("button", { name: t("Save API credential"), exact: true }).click();
    await expect.poll(() => saved).toEqual({ api_key: "fixture-key-not-a-live-secret", confirm_billing: true });
    await expect(dialog).toContainText(t("Credential saved. Model access remains unverified until an analysis succeeds."));
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("fixture-key-not-a-live-secret");
    expect(inference).toEqual([]);
    await dialog.getByRole("button", { name: t("Close"), exact: true }).click();
    await page.getByRole("button", { name: t("Change account"), exact: true }).click();
    await dialog.getByRole("button", { name: t("Use a Gemini API key"), exact: true }).click();
    await expect(field).toHaveValue("");
    await expect(dialog.getByRole("checkbox")).not.toBeChecked();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await dialog.screenshot({ path: "../.local/v27-ui/auth-" + language + "-" + info.project.name + ".png", animations: "disabled" });
  });

  test("failed Gemini key setup clears the field and redacts echoed credentials in " + language, async ({ page }) => {
    await setup(page, language);
    await page.route("**/api/ai-connections/3/auth/api-key", route => route.fulfill({ status: 503, json: { detail: "Synthetic failure: fixture-key-not-a-live-secret" } }));
    await openConnections(page);
    await page.locator("#ai-connection-3 .action-menu > summary").click();
    await page.getByRole("button", { name: t("Change account"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Sign in with") + " Antigravity", exact: true });
    await dialog.getByRole("button", { name: t("Use a Gemini API key"), exact: true }).click();
    const field = dialog.getByLabel(t("Gemini API key"), { exact: true });
    await field.fill("fixture-key-not-a-live-secret");
    await dialog.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: t("Save API credential"), exact: true }).click();
    await expect(dialog.getByRole("alert")).toHaveText("Synthetic failure: [redacted]");
    await expect(field).toHaveValue("");
    await expect(dialog).not.toContainText("fixture-key-not-a-live-secret");
    await expect(dialog).not.toContainText(t("Credential saved. Model access remains unverified until an analysis succeeds."));
  });

  test("missing Antigravity runtime has an explicit error and unknown quota in " + language, async ({ page }) => {
    await setup(page, language, [assistant({ status: "DISCONNECTED", availability: "ERROR", error: "Antigravity CLI is unavailable or incompatible." })]);
    await page.route("**/api/ai-connections/3/auth/api-key", route => route.fulfill({ status: 503, json: { detail: "Antigravity CLI is unavailable or incompatible." } }));
    await openConnections(page);
    await expect(page.getByRole("region", { name: t("AI connections"), exact: true }).getByText(t("Antigravity CLI is unavailable or incompatible."), { exact: true })).toBeVisible();
    const sidebar = page.getByRole("complementary", { name: t("Instance navigation"), exact: true });
    await expect(sidebar.locator('[data-connection="3"]')).toContainText("Antigravity");
    await expect(sidebar.locator('[data-connection="3"] [data-provider="antigravity"]')).toBeVisible();
    await expect(sidebar.locator('[data-connection="3"] [role="meter"]')).toHaveCount(0);
    await page.getByRole("button", { name: t("Connect with") + " Antigravity", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: t("Sign in with") + " Antigravity", exact: true });
    await dialog.getByRole("button", { name: t("Use a Gemini API key"), exact: true }).click();
    await dialog.getByLabel(t("Gemini API key"), { exact: true }).fill("fixture-only-unavailable-key");
    await dialog.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: t("Save API credential"), exact: true }).click();
    await expect(dialog.getByRole("alert")).toHaveText(t("Antigravity CLI is unavailable or incompatible."));
    await expect(dialog).not.toContainText(t("Connection successful."));
  });

  test("Antigravity tool refusal remains partial with correct attribution in " + language, async ({ page }, info) => {
    await setup(page, language);
    await page.route("**/api/queue", route => route.fulfill({ json: [{
      id: 27, kind: "analysis", workflow: "question", title: "Fixture permission review",
      request_id: "fixture-question", status: "DONE", queue_state: "DONE", request_status: "PARTIAL",
      result_status: "partial", result_limits: ["Antigravity denied a tool required for this analysis."],
      assignments: [{ connection_id: 3, connection_name: "", agent: "antigravity", model: model.identifier, public_role: "verifier" }],
      assignment_state: "previous", stage: "Analysis completed", public_role: "verifier",
      href: "/questions/fixture-question", environment_name: "Fixture", elapsed_seconds: 12,
    }] }));
    await page.goto("/questions");
    const sidebar = page.getByRole("complementary", { name: t("Instance navigation"), exact: true });
    await expect(sidebar.locator('[data-connection="3"]')).toContainText(t("Quota unknown"));
    await expect(sidebar.locator('[data-connection="3"] [role="meter"]')).toHaveCount(0);
    if (info.project.name === "mobile") await page.getByRole("button", { name: t("Task queue"), exact: true }).click();
    const queue = page.getByRole(info.project.name === "mobile" ? "dialog" : "complementary", { name: t("Task queue"), exact: true });
    await queue.getByRole("button", { name: new RegExp("^" + t("Completed") + " \\(1\\)$") }).click();
    const card = queue.locator('[data-job="27"]');
    await expect(card.locator(".queue-assistant-name")).toHaveText("Antigravity");
    await expect(card.locator('[data-provider="antigravity"]')).toBeVisible();
    await expect(card.locator(".queue-role")).toHaveText(t("Verifier"));
    await expect(card.locator(".queue-model")).toHaveAttribute("title", "Antigravity · " + model.identifier);
    await expect(card.locator('[data-result-status="partial"]')).toContainText(t("Partial result"));
    await expect(card).toContainText(t("Antigravity denied a tool required for this analysis."));
    await expect(card).not.toContainText(t("Complete result"));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await queue.screenshot({ path: "../.local/v27-ui/queue-" + language + "-" + info.project.name + ".png", animations: "disabled" });
  });
}
