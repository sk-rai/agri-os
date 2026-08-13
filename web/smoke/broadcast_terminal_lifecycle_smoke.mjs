import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const token = process.env.WEB_SWEEP_TOKEN;
const tenantId = process.env.WEB_SWEEP_TENANT_ID || "android-fpo-multi-village-test";
const actorId = process.env.WEB_SWEEP_ACTOR_ID;

if (!token || !actorId) {
  console.error("Missing WEB_SWEEP_TOKEN / WEB_SWEEP_ACTOR_ID. Generate them with create_web_ui_smoke_session.py.");
  process.exit(1);
}

const projectId = process.env.FPO_PROJECT_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002001";
const campaignId = process.env.FPO_CLOSURE_CAMPAIGN_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002950";
const selectedFarmerId = process.env.FPO_SELECTED_FARMER_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002106";
const terminalStatus = (process.env.BROADCAST_TERMINAL_STATUS || "EXPIRED").toUpperCase();
const expectedAuditAction = terminalStatus === "CANCELLED" ? "CANCEL_CAMPAIGN" : "EXPIRE_CAMPAIGN";
const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const broadcastUrl = `${baseUrl}/broadcasts`;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1680, height: 1400 } });

await page.addInitScript(({ token, tenantId, actorId }) => {
  window.localStorage.setItem("agrios_token", token);
  window.localStorage.setItem("agrios_tenant_id", tenantId);
  window.localStorage.setItem("agrios_user_id", actorId);
  window.localStorage.setItem("agrios_role", "ENTERPRISE_ADMIN");
}, { token, tenantId, actorId });

await page.goto(broadcastUrl, { waitUntil: "domcontentloaded" });

async function apiFetch(pathname) {
  return page.evaluate(
    async ({ apiBaseUrl, pathname, token, tenantId, actorId }) => {
      const response = await fetch(`${apiBaseUrl}${pathname}`, {
        headers: {
          "Authorization": `Bearer ${token}`,
          "X-Tenant-ID": tenantId,
          "X-Actor-ID": actorId,
        },
      });
      const text = await response.text();
      let body = null;
      try {
        body = text ? JSON.parse(text) : null;
      } catch {
        body = text;
      }
      return { status: response.status, body };
    },
    { apiBaseUrl, pathname, token, tenantId, actorId }
  );
}

function assertApi(label, response, predicate, detailBuilder = (body) => body) {
  if (response.status !== 200) {
    throw new Error(`${label} API returned ${response.status}: ${JSON.stringify(response.body).slice(0, 700)}`);
  }
  if (!predicate(response.body)) {
    throw new Error(`${label} API predicate failed: ${JSON.stringify(detailBuilder(response.body)).slice(0, 1800)}`);
  }
}

async function applyFilters() {
  await page.getByLabel("Project ID").fill(projectId);
  await page.getByLabel("Status").selectOption(terminalStatus);
  await page.getByRole("button", { name: "Apply filters" }).click();
}

try {
  const campaignApi = await apiFetch(`/api/v1/broadcasts/${campaignId}`);
  assertApi("campaign detail", campaignApi, (body) => {
    return body.status === terminalStatus && body.project_id === projectId && (body.delivery_summary || {}).total === 12;
  }, (body) => ({ status: body.status, project_id: body.project_id, delivery_summary: body.delivery_summary, expires_at: body.expires_at }));

  const feedApi = await apiFetch(`/api/v1/broadcasts/farmers/${selectedFarmerId}/broadcasts?language_code=en&include_read=true`);
  assertApi("farmer feed", feedApi, (body) => body.count === 0, (body) => body);

  const auditApi = await apiFetch(`/api/v1/broadcasts/${campaignId}/audit?limit=100`);
  assertApi("broadcast audit", auditApi, (body) => {
    const actions = new Set((body.events || []).map((row) => row.action));
    return actions.has(expectedAuditAction);
  }, (body) => ({ count: body.count, actions: (body.events || []).map((row) => row.action) }));

  await page.goto(broadcastUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Broadcasts", exact: true }).waitFor({ timeout: 20000 });
  await applyFilters();
  await page.getByText("FPO project closure migration notice").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText(campaignId).first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText(terminalStatus).first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByRole("button", { name: "View" }).first().click();

  await page.getByRole("heading", { name: "Broadcast detail" }).waitFor({ timeout: 20000 });
  await page.getByText("Delivery lifecycle").waitFor({ timeout: 20000 });
  await page.getByText("Total").waitFor({ timeout: 20000 });
  await page.getByText("12").first().waitFor({ timeout: 20000 });
  await page.getByRole("button", { name: "Load audit" }).click();
  await page.getByText("audit event(s) returned").waitFor({ timeout: 20000 });
  await page.getByText(expectedAuditAction).waitFor({ timeout: 20000 });

  const screenshotPath = path.join(screenshotDir, `broadcast-terminal-${terminalStatus.toLowerCase()}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "broadcast_terminal_lifecycle_web_smoke.v1",
    status: "PASSED",
    url: broadcastUrl,
    screenshot: screenshotPath,
    tenant_id: tenantId,
    actor_id: actorId,
    project_id: projectId,
    campaign_id: campaignId,
    terminal_status: terminalStatus,
    evidence: {
      broadcast_terminal_campaign_visible_in_admin: true,
      broadcast_terminal_status: campaignApi.body.status,
      broadcast_terminal_delivery_total_preserved: campaignApi.body.delivery_summary.total,
      broadcast_terminal_farmer_feed_count: feedApi.body.count,
      broadcast_terminal_audit_action_visible: expectedAuditAction,
    },
    api_cross_check_passed: true,
  }, null, 2));
} catch (error) {
  const screenshotPath = path.join(screenshotDir, `broadcast-terminal-${terminalStatus.toLowerCase()}-failure.png`);
  try {
    await page.screenshot({ path: screenshotPath, fullPage: true });
  } catch {
    // Best effort only.
  }
  console.error(JSON.stringify({
    schema_version: "broadcast_terminal_lifecycle_web_smoke_failure.v1",
    status: "FAILED",
    screenshot: screenshotPath,
    terminal_status: terminalStatus,
    message: error instanceof Error ? error.message : String(error),
    body_text_sample: (await page.locator("body").innerText().catch(() => "")).slice(0, 5000),
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}