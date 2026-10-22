import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

async function base(page: Page, language = "en") {
  await page.route("**/api/settings", r => r.fulfill({ json: { name: "SpecHelper", primary_color: "#2563eb", short_label: "", allow_confrontation: true, language } }));
  await page.route("**/api/connections", r => r.fulfill({ json: { github: { status: "CONNECTED" }, ais: [], databases: [] } }));
  await page.route("**/api/system", r => r.fulfill({ json: { jobs: [] } }));
  await page.route("**/api/queue", r => r.fulfill({ json: [] }));
  await page.route(/\/api\/ticket-connectors(?:\?.*)?$/, r => r.fulfill({ json: [] }));
  await page.route("**/api/environments", r => r.fulfill({ json: [{ id: 91, name: "Java service and Python worker", status: "READY", revision: 1, repositories: [], database_id: null, database_name: null, error: "" }] }));
}

test("environment instructions and durable documents can be changed independently of request attachments", async ({ page }) => {
  await base(page);
  let value = { instructions: "Review the active implementation", instructions_enabled: true, revision: 1, max_files: 20, max_file_size: 26214400, resources: [] as { id: string; name: string; enabled: boolean; filename: string; content_type: string; size: number; sha256: string; version: number; version_id: string; updated_at: string; preview: string; agent_readable: boolean }[] };
  const methods: string[] = [];
  await page.route("**/api/environments/91/context**", async route => {
    const request = route.request();
    if (request.method() === "GET") return route.fulfill({ json: value });
    methods.push(request.method());
    if (request.method() === "PUT") {
      const body = request.postDataJSON();
      expect(body.expected_revision).toBe(value.revision);
      value = { ...value, ...body, revision: value.revision + 1 };
    } else if (request.method() === "POST") {
      expect(request.headers()["content-type"]).toContain("multipart/form-data");
      expect(request.postDataBuffer()?.toString()).toContain('name="expected_revision"');
      const version = value.resources.length ? 2 : 1;
      value = { ...value, revision: value.revision + 1, resources: [{ id: "resource-1", name: "architecture.md", enabled: true, filename: "architecture.md", content_type: "text/markdown", size: 32, sha256: String(version).repeat(64), version, version_id: `version-${version}`, updated_at: "2026-10-22T12:00:00Z", preview: version === 1 ? "The Java API calls the Python worker." : "The Python worker uses the event queue.", agent_readable: true }] };
    } else if (request.method() === "PATCH") {
      expect(request.postDataJSON().expected_revision).toBe(value.revision);
      value = { ...value, revision: value.revision + 1, resources: value.resources.map(r => ({ ...r, enabled: request.postDataJSON().enabled })) };
    } else if (request.method() === "DELETE") {
      expect(new URL(request.url()).searchParams.get("expected_revision")).toBe(String(value.revision));
      value = { ...value, revision: value.revision + 1, resources: [] };
    }
    return route.fulfill({ json: value });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  await page.getByText("Environment context", { exact: true }).click();
  await expect(page.getByLabel("Short environment instructions")).toHaveValue("Review the active implementation");
  await page.getByLabel("Short environment instructions").fill("Check Java and Python source references.");
  await expect(page.getByLabel("Add reference document")).toBeDisabled();
  await page.getByLabel("Use environment instructions", { exact: true }).uncheck();
  await page.getByRole("button", { name: "Save context instructions" }).click();
  await expect(page.getByLabel("Use environment instructions", { exact: true })).not.toBeChecked();
  await page.getByLabel("Add reference document").setInputFiles({ name: "architecture.md", mimeType: "text/markdown", buffer: Buffer.from("The Java API calls the Python worker.") });
  await page.getByText("Text preview", { exact: true }).click();
  await expect(page.getByText("The Java API calls the Python worker.", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download document" })).toHaveAttribute("href", "/api/environments/91/context/resources/resource-1/versions/version-1/download");
  await page.getByLabel("Use architecture.md", { exact: true }).uncheck();
  await expect(page.getByLabel("Use architecture.md", { exact: true })).not.toBeChecked();
  await page.getByLabel("Replace architecture.md", { exact: true }).setInputFiles({ name: "architecture.md", mimeType: "text/markdown", buffer: Buffer.from("The Python worker uses the event queue.") });
  await expect(page.getByRole("link", { name: "Download document" })).toHaveAttribute("href", /version-2/);
  await expect(page.getByText("The Python worker uses the event queue.", { exact: true })).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Remove architecture.md", exact: true }).click();
  await expect(page.getByText("No environment reference documents.", { exact: true })).toBeVisible();
  expect(methods).toEqual(["PUT", "POST", "PATCH", "POST", "DELETE"]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("French context form shows unreadable files and recovers from stale revisions without losing edits", async ({ page }) => {
  await base(page, "fr");
  let revision = 1;
  await page.route("**/api/environments/91/context", route => {
    if (route.request().method() === "PUT") {
      revision = 2;
      return route.fulfill({ status: 409, json: { detail: "The environment context has changed. Refresh before editing." } });
    }
    return route.fulfill({ json: { instructions: revision === 1 ? "Original" : "Saved elsewhere", instructions_enabled: true, revision, max_files: 20, max_file_size: 26214400, resources: [{ id: "binary", name: "legacy.txt", filename: "legacy.txt", enabled: true, content_type: "text/plain", size: 3, sha256: "f".repeat(64), version: 1, version_id: "binary-v1", updated_at: "2026-10-22T12:00:00Z", preview: "", agent_readable: false }] } });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Environnements", exact: true }).click();
  await page.getByText("Contexte de l’environnement", { exact: true }).click();
  await expect(page.getByText("Ce format n’est pas lisible par l’agent. Remplacez-le par un document pris en charge.", { exact: true })).toBeVisible();
  const instructions = page.getByLabel("Instructions courtes de l’environnement");
  await instructions.fill("Local draft");
  await page.getByRole("button", { name: "Enregistrer les instructions du contexte" }).click();
  await expect(instructions).toHaveValue("Local draft");
  await page.getByRole("button", { name: "Recharger le contexte" }).click();
  await expect(instructions).toHaveValue("Saved elsewhere");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("historical result context remains versioned and distinguishes observed reads from missing telemetry", async ({ page }) => {
  await base(page);
  const id = "66666666-6666-4666-8666-666666666666";
  const snapshot = (version: number) => ({ schema_version: 1, snapshot_id: `snapshot-${version}`, environment: { id: 91, name: "Java service and Python worker", revision: version }, instructions: { text: `Architecture rules ${version}`, enabled: true, sha256: String(version).repeat(64) }, resources: [{ id: "architecture", version_id: `document-${version}`, name: "architecture.md", filename: "architecture.md", version, sha256: String(version).repeat(64), content_type: "text/markdown", size: 77, agent_readable: true }] });
  const usage = [{ version_id: "document-1", public_role: "analyst", status: "observed" }, { version_id: "document-1", public_role: "counter_analyst", status: "not_observed" }, { version_id: "document-1", public_role: "verifier", status: "unavailable" }];
  const result = (version: number) => ({ id: `result-${version}`, number: version, run_number: version, format_version: "1.2", language: "en", status: "READY", created_at: "2026-10-22T12:00:00Z", ticket: { title: `Proposal ${version}`, context: "Preserve compatibility" }, markdown: `Proposal ${version}`, goal_markdown: "", artifacts: {}, context_snapshot: snapshot(version), context_usage: version === 1 ? usage : [] });
  await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: { id, need: "Review the event delivery", status: "READY", environment_name: "Java service and Python worker", language: "en", confrontation: true, baseline: [], database: {}, questions: [], conversation: [], understanding: "", progress: [], error: "", attachments: [{ id: "request-only", name: "request-screenshot.png", size: 15 }], ticket: result(2).ticket, markdown: "Proposal 2", latest_version: result(2), versions: [{ number: 1 }, { number: 2 }], messages: [], analysis_runs: [{ number: 1, status: "DONE", context_snapshot: snapshot(1), context_usage: usage, steps: [] }, { number: 2, status: "DONE", context_snapshot: snapshot(2), context_usage: [], steps: [] }] } }));
  await page.route(`**/api/requests/${id}/versions/1`, route => route.fulfill({ json: result(1) }));
  await page.goto(`/requests/${id}?version=1`);
  await expect(page.getByRole("heading", { name: "Proposal 1", exact: true })).toBeVisible();
  const context = page.getByText("Frozen analysis context", { exact: true }).first().locator("..");
  await context.locator("summary").first().click();
  await expect(context.getByText("Context revision 1", { exact: false })).toBeVisible();
  await expect(context.getByRole("link", { name: "Download frozen document" })).toHaveAttribute("href", `/api/requests/${id}/runs/1/context/document-1/download`);
  await expect(context.getByText("Analyst · Read observed", { exact: true })).toBeVisible();
  await expect(context.getByText("Counter-analyst · No read observed", { exact: true })).toBeVisible();
  await expect(context.getByText("Verifier · Read telemetry unavailable", { exact: true })).toBeVisible();
  await expect(context.getByText("2".repeat(64), { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "request-screenshot.png" })).toHaveAttribute("href", `/api/requests/${id}/attachments/request-only`);
  await page.getByLabel("Result version", { exact: true }).selectOption("latest");
  await expect(page.getByRole("heading", { name: "Proposal 2", exact: true })).toBeVisible();
  const latest = page.getByText("Frozen analysis context", { exact: true }).first().locator("..");
  await expect(latest.getByRole("link", { name: "Download frozen document" })).toHaveAttribute("href", `/api/requests/${id}/runs/2/context/document-2/download`);
  await expect(latest.getByText("Read telemetry unavailable", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
