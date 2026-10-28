import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import en from "../src/locales/en.json";
import fr from "../src/locales/fr.json";

const id = "25252525-2525-4252-8252-252525252525";
const consulted = "2026-10-24T08:15:00Z";
const digest = "a".repeat(64);
const safeExcerpt = "Keep audit records. <script>window.__webInjected=true</script>";
const receiptId = "web-" + "b".repeat(32);
const otherReceiptId = "web-" + "c".repeat(32);
const urls = ["https://www.service-public.fr/particuliers/vosdroits", "https://www.legifrance.gouv.fr"];
const dictionary = (language: "en" | "fr", key: string) => (language === "fr" ? fr : en)[key as keyof typeof en] || key;
async function setup(page: Page, language: "en" | "fr") {
  await page.route("**/api/**", route => route.fulfill({ json: [] }));
  await page.route("**/api/access/session", route => route.fulfill({ json: { mode: "local", authenticated: true, csrf_token: "", expires_at: null } }));
  await page.route("**/api/settings", route => route.fulfill({ json: { name: "SpecHelper", language, primary_color: "#2563eb" } }));
  await page.route("**/api/connections", route => route.fulfill({ json: { github: { status: "CONNECTED" }, ais: [], databases: [] } }));
  await page.route("**/api/orchestration-settings", route => route.fulfill({ json: { reliability_protocol: "2.4", global_instructions: "Consult relevant official references when an external obligation matters.", global_instruction_version: 1, max_calls: 12, allow_same_family_fallback: true } }));
  await page.route("**/api/environments", route => route.fulfill({ json: [{ id: 1, name: "Production", status: "READY", repositories: [], revision: 1 }] }));
  await page.addInitScript(theme => localStorage.setItem("spechelper-theme", theme), language === "fr" ? "dark" : "light");
}
function configuration(revision = 1, references: { url: string; note: string }[] = []) {
  return { instructions: "Archived contracts are retained for audit.", instructions_enabled: true, official_references: references, revision, resources: [], max_files: 20, max_file_size: 26214400 };
}
async function contextPanel(page: Page, language: "en" | "fr") {
  const t = (key: string) => dictionary(language, key);
  await page.goto("/admin");
  await page.getByRole("button", { name: t("Sources & environments"), exact: true }).click();
  await page.getByRole("button", { name: t("Environments"), exact: true }).click();
  await page.getByText(t("Environment context"), { exact: true }).click();
  return page.locator("details").filter({ has: page.locator("summary").filter({ hasText: new RegExp(`^${t("Environment context")}$`) }) });
}
const baseScope = { environment: "Production", conditions: ["Current deployed release"], period: "2026-10", population: "Configured deployment", sample_limits: "Only the declared scope was checked." };
function report(missingReceipt = false) {
  return { blocking: missingReceipt, database: { status: "not_configured", scope: "", limitations: [], checks: [] }, limitations: missingReceipt ? ["The source has no publication or effective date; present applicability is not established."] : ["A documented obligation does not prove this deployment follows it."], web_references: missingReceipt ? [] : [{ reference_id: receiptId, url: urls[1] + "/guide", title: "Official retention guidance 2026", consulted_at: consulted, published_at: "2026-09-01", sha256: digest, text_sha256: "d".repeat(64), text: "Applicable from 2026-10-01. Release 2026.2. " + safeExcerpt, truncated: false, status: "checked" }], claims: [{ id: "official-1", statement: missingReceipt ? "The undated reference does not establish a current obligation." : "The official guidance describes retention for this jurisdiction.", kind: missingReceipt ? "unknown" : "interpretation", status: missingReceipt ? "unverified" : "supported", basis: "official_rule", scope: baseScope, sources: [{ kind: "web", reference_id: missingReceipt ? otherReceiptId : receiptId, authority: "Official public documentation", effective_date: missingReceipt ? "" : "2026-10-01", version: missingReceipt ? "" : "2026.2", jurisdiction: "France", scope: "Employment records", applicability: missingReceipt ? "unknown" : "current", applicability_notes: missingReceipt ? "No dated text is available; no present legal applicability is claimed." : "The text applies to the selected period and record category.", excerpt: missingReceipt ? "Undated external text." : safeExcerpt }], counterexamples: [], verification_notes: "The documented rule and the deployed implementation are separate observations.", universal: false, material: true }, { id: "deployment-1", statement: "The deployed code retains audit entries behind the configured flag.", kind: "observed", status: "supported", basis: "deployment", scope: baseScope, sources: [{ kind: "git", repository: "app", commit: "e".repeat(40), path: "retention.py", symbol: "should_retain", line_start: 1, line_end: 2, excerpt: "return flags.keep_audit" }], counterexamples: [], verification_notes: "No business database was queried.", universal: false, material: true }] };
}
function snapshot(version = 1) {
  return { schema_version: 1, snapshot_id: `snapshot-${version}`, analysis_protocol: "2.4", environment: { id: 1, name: "Production at analysis", revision: version }, instructions: { enabled: true, mode: "factual", text: `Frozen context ${version}`, sha256: digest }, official_references: [{ url: `https://www.legifrance.gouv.fr/frozen-${version}`, note: `Frozen official source note ${version}` }], resources: [{ id: "resource-1", version_id: "document-v1", name: "Retention policy", filename: "policy.md", version: 1, sha256: digest, size: 350, content_type: "text/markdown", agent_readable: true }] };
}
function result(number = 1, missingReceipt = false) {
  return { id: `version-${number}`, number, format_version: "1.2", language: "en", status: missingReceipt ? "PARTIAL" : "READY", created_at: consulted, ticket: { title: `Reviewed retention ${number}`, context: "Preserve the checked distinction between official guidance and deployment.", need: "Understand retention rules.", proposed_solution: "Retain explicit scope and limits." }, markdown: "# Frozen ticket", goal_markdown: "# Frozen goal", artifacts: {}, evidence: report(missingReceipt), run_number: number, context_snapshot: snapshot(number), context_usage: [{ version_id: "document-v1", public_role: "counter_analyst", status: "observed" }, { version_id: "document-v1", public_role: "verifier", status: "unavailable" }] };
}
function requestDetail(latest = result(2)) {
  return { id, workflow: "request", analysis_protocol: "2.4", need: "Understand retention rules.", status: latest.status, language: "en", environment_id: 1, environment_name: "Production", created_at: consulted, confrontation: true, baseline: [], database: {}, questions: [], conversation: [], progress: [], understanding: "Separate obligations from observations.", error: "", attachments: [], ticket: latest.ticket, markdown: latest.markdown, versions: [{ number: latest.number, status: latest.status, created_at: consulted }, { number: 1, status: "READY", created_at: consulted }], latest_version: latest, messages: [] };
}
for (const language of ["en", "fr"] as const) {
  const t = (key: string) => dictionary(language, key);
  test(`official reference URLs and domains save with notes and persist in ${language}`, async ({ page }, info) => {
    await setup(page, language);
    let current = configuration(); const saves: Record<string, unknown>[] = [];
    await page.route("**/api/environments/1/context", route => {
      if (route.request().method() === "PUT") {
        const body = route.request().postDataJSON(); saves.push(body); current = { ...current, ...body, revision: current.revision + 1, official_references: body.official_references.map((item: { url: string; note: string }) => ({ ...item, url: item.url.startsWith("https://") ? item.url : "https://" + item.url })) };
      }
      return route.fulfill({ json: current });
    });
    let context = await contextPanel(page, language);
    const references = context.getByRole("region", { name: t("Official reference sources"), exact: true });
    await references.getByRole("button", { name: t("Add official reference"), exact: true }).click();
    await references.getByLabel(t("Reference URL or domain"), { exact: true }).fill(urls[0]);
    await references.getByLabel(t("Reference note"), { exact: true }).fill("Public service guidance; verify applicability to the request.");
    await references.getByRole("button", { name: t("Add official reference"), exact: true }).click();
    await references.getByLabel(t("Reference URL or domain"), { exact: true }).nth(1).fill("www.legifrance.gouv.fr");
    await references.getByLabel(t("Reference note"), { exact: true }).nth(1).fill("Check the effective text and jurisdiction.");
    await context.getByRole("button", { name: t("Save business context"), exact: true }).click();
    await expect.poll(() => saves[0]).toMatchObject({ expected_revision: 1, instructions: "Archived contracts are retained for audit.", instructions_enabled: true, official_references: [{ url: urls[0], note: "Public service guidance; verify applicability to the request." }, { url: "www.legifrance.gouv.fr", note: "Check the effective text and jurisdiction." }] });
    await expect(context.getByRole("status")).toContainText(t("Environment context saved. Existing analyses remain unchanged."));
    await expect(references.getByLabel(t("Reference URL or domain"), { exact: true }).nth(1)).toHaveValue(urls[1]);
    await page.reload(); context = await contextPanel(page, language);
    await expect(context.getByLabel(t("Reference URL or domain"), { exact: true })).toHaveCount(2);
    await expect(context.getByLabel(t("Reference note"), { exact: true }).nth(1)).toHaveValue("Check the effective text and jurisdiction.");
    await expect(context.getByText(t("Optional public URLs or domains and applicability notes. These are starting points, not an exclusive list or assistant instructions."), { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await context.screenshot({ path: `../.local/v25-ui/web-references-${language}-${info.project.name}.png`, animations: "disabled" });
  });
  test(`missing URL, rejected destination and stale official-reference edits remain correctable in ${language}`, async ({ page }) => {
    await setup(page, language); let puts = 0; let stale = false; let current = configuration();
    await page.route("**/api/environments/1/context", route => {
      if (route.request().method() !== "PUT") return route.fulfill({ json: current });
      puts++; return route.fulfill({ status: stale ? 409 : 422, json: { detail: stale ? "The environment context has changed. Refresh before editing." : "Use a public HTTPS reference URL without credentials." } });
    });
    const context = await contextPanel(page, language);
    await context.getByRole("button", { name: t("Add official reference"), exact: true }).click();
    await context.getByLabel(t("Reference note"), { exact: true }).fill("Missing URL needs correction.");
    await context.getByRole("button", { name: t("Save business context"), exact: true }).click();
    expect(puts).toBe(0);
    await expect(context.getByLabel(t("Reference URL or domain"), { exact: true })).toBeFocused();
    await context.getByLabel(t("Reference URL or domain"), { exact: true }).fill("https://127.0.0.1/private");
    await context.getByRole("button", { name: t("Save business context"), exact: true }).click();
    await expect(context.getByRole("alert")).toContainText(t("Use a public HTTPS reference URL without credentials."));
    await expect(context.getByLabel(t("Reference note"), { exact: true })).toHaveValue("Missing URL needs correction.");
    stale = true;
    await context.getByLabel(t("Reference URL or domain"), { exact: true }).fill(urls[0]);
    await context.getByRole("button", { name: t("Save business context"), exact: true }).click();
    await expect(context.getByRole("alert")).toContainText(t("The environment context has changed. Refresh before editing."));
    await expect(context.getByLabel(t("Reference URL or domain"), { exact: true })).toHaveValue(urls[0]);
    current = configuration(3, [{ url: urls[1], note: "Another browser saved this current reference." }]);
    await context.getByRole("button", { name: t("Reload context"), exact: true }).click();
    await expect(context.getByLabel(t("Reference URL or domain"), { exact: true })).toHaveValue(urls[1]);
    await expect(context.getByLabel(t("Reference note"), { exact: true })).toHaveValue("Another browser saved this current reference.");
    expect(puts).toBe(2);
  });
  test(`official-reference loading failure remains retryable without false saved state in ${language}`, async ({ page }) => {
    await setup(page, language); let available = false;
    await page.route("**/api/environments/1/context", route => available ? route.fulfill({ json: configuration(2, [{ url: urls[1], note: "Recovered reference." }]) }) : route.fulfill({ status: 503, json: { detail: "Reference metadata unavailable." } }));
    const context = await contextPanel(page, language);
    await expect(context.getByRole("alert")).toContainText("Reference metadata unavailable.");
    await expect(context.getByText(t("Environment context saved. Existing analyses remain unchanged."), { exact: true })).toHaveCount(0);
    available = true; await context.getByRole("button", { name: t("Reload context"), exact: true }).click();
    await expect(context.getByLabel(t("Reference URL or domain"), { exact: true })).toHaveValue(urls[1]);
    await expect(context.getByRole("alert")).toHaveCount(0);
  });
  test(`Web observations retain dated provenance and stay separate from deployment behavior in ${language}`, async ({ page }, info) => {
    await setup(page, language); const value = requestDetail(); await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: value }));
    await page.goto(`/requests/${id}`);
    await page.getByText(t("Verification details"), { exact: true }).click();
    const official = page.getByRole("article", { name: "The official guidance describes retention for this jurisdiction.", exact: true });
    const deployed = page.getByRole("article", { name: "The deployed code retains audit entries behind the configured flag.", exact: true });
    await expect(official).toContainText(t("Official rule")); await expect(deployed).toContainText(t("Deployment observation"));
    await official.getByText(t("Sources and verification details"), { exact: true }).click();
    const link = official.getByRole("link", { name: "Official retention guidance 2026", exact: true });
    await expect(link).toHaveAttribute("href", urls[1] + "/guide"); await expect(link).toHaveAttribute("target", "_blank"); await expect(link).toHaveAttribute("rel", /noopener/);
    await expect(official).toContainText(`${t("Consulted on")}: ${consulted}`);
    await expect(official).toContainText(digest);
    await expect(official).toContainText("2026-10-01 · 2026.2 · France · Employment records");
    await expect(official).toContainText("The text applies to the selected period and record category.");
    await expect(official.locator("blockquote")).toHaveText(safeExcerpt);
    await expect(official.locator("script")).toHaveCount(0);
    expect(await page.evaluate(() => (window as Window & { __webInjected?: boolean }).__webInjected)).toBeUndefined();
    await deployed.getByText(t("Sources and verification details"), { exact: true }).click();
    await expect(deployed).toContainText("retention.py"); await expect(deployed).not.toContainText("Official retention guidance");
    const findings = page.getByLabel(t("Analysis findings and limits"), { exact: true });
    await expect(findings).toContainText("A documented obligation does not prove this deployment follows it.");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await findings.screenshot({ path: `../.local/v25-ui/web-evidence-${language}-${info.project.name}.png`, animations: "disabled" });
  });
  test(`historical frozen reference hints and observed role reads survive environment changes in ${language}`, async ({ page }) => {
    await setup(page, language); const value = requestDetail(); const historical = result(1);
    await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: value }));
    await page.route(`**/api/requests/${id}/versions/1`, route => route.fulfill({ json: historical }));
    await page.route("**/api/environments/1/context", route => route.fulfill({ json: configuration(9, [{ url: "https://www.service-public.fr/current-only", note: "CURRENT_ENVIRONMENT_ONLY" }]) }));
    await page.goto(`/requests/${id}?version=1`);
    await page.getByText(t("Frozen analysis context"), { exact: true }).click();
    const frozen = page.locator("details").filter({ has: page.locator("summary").filter({ hasText: new RegExp(`^${t("Frozen analysis context")}$`) }) });
    await expect(frozen.getByRole("link", { name: "https://www.legifrance.gouv.fr/frozen-1", exact: true })).toHaveAttribute("href", "https://www.legifrance.gouv.fr/frozen-1");
    await expect(frozen).toContainText("Frozen official source note 1"); await expect(frozen).not.toContainText("CURRENT_ENVIRONMENT_ONLY");
    await expect(frozen).toContainText(t("Context revision {number}").replace("{number}", "1"));
    await expect(frozen.getByLabel(t("Document read observations"), { exact: true })).toContainText(`${t("Counter-analyst")} · ${t("Read observed")}`);
    await expect(frozen.getByLabel(t("Document read observations"), { exact: true })).toContainText(`${t("Verifier")} · ${t("Read telemetry unavailable")}`);
    await expect(frozen.getByRole("link", { name: t("Download frozen document"), exact: true })).toHaveAttribute("href", `/api/requests/${id}/runs/1/context/document-v1/download`);
    await page.getByLabel(t("Result version"), { exact: true }).selectOption("latest");
    await expect(page.getByRole("heading", { name: "Reviewed retention 2", exact: true })).toBeVisible();
    if (await frozen.getAttribute("open") === null) await page.getByText(t("Frozen analysis context"), { exact: true }).click();
    await expect(page.getByRole("link", { name: "https://www.legifrance.gouv.fr/frozen-2", exact: true })).toBeVisible();
    await expect(page.getByText("Frozen official source note 1", { exact: true })).toHaveCount(0);
  });
  test(`historical missing Web receipt and undated applicability remain explicitly unverified in ${language}`, async ({ page }) => {
    await setup(page, language); const historical = result(1, true); historical.context_snapshot = {} as ReturnType<typeof snapshot>;
    await page.route(`**/api/requests/${id}`, route => route.fulfill({ json: requestDetail() }));
    await page.route(`**/api/requests/${id}/versions/1`, route => route.fulfill({ json: historical }));
    await page.goto(`/requests/${id}?version=1`);
    await expect(page.getByText(t("Environment context was not recorded for this historical analysis."), { exact: true })).toBeVisible();
    await page.getByText(t("Verification details"), { exact: true }).click();
    const claim = page.getByRole("article", { name: "The undated reference does not establish a current obligation.", exact: true });
    await expect(claim).toContainText(t("Not verified"));
    await claim.getByText(t("Sources and verification details"), { exact: true }).click();
    await expect(claim).toContainText(t("The external reference observation is unavailable."));
    await expect(claim).toContainText("No dated text is available; no present legal applicability is claimed.");
    await expect(claim.getByRole("link")).toHaveCount(0); await expect(claim).not.toContainText(t("Consulted on"));
    await expect(page.getByLabel(t("Result reliability"), { exact: true })).toContainText(t("Partial result"));
  });
}
