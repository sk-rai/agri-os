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
  await page.getByLabel("Status").selectOption("PUBLISHED");
  await page.getByRole("button", { name: "Apply filters" }).click();
}

try {
  const campaignApi = await apiFetch(`/api/v1/broadcasts/${campaignId}`);
  assertApi("campaign detail", campaignApi, (body) => {
    const summary = body.delivery_summary || {};
    const metadata = body.metadata || {};
    return body.status === "PUBLISHED"
      && summary.total === 12
      && summary.pending === 11
      && summary.read === 1
      && summary.acknowledged === 1
      && metadata.last_delivery_retry_retried === 11
      && metadata.last_delivery_retry_skipped_acknowledged === 1;
  }, (body) => ({ delivery_summary: body.delivery_summary, metadata: body.metadata }));

  const pendingApi = await apiFetch(`/api/v1/broadcasts/${campaignId}/deliveries?status=PENDING&limit=100`);
  assertApi("pending deliveries", pendingApi, (body) => {
    return body.count === 11 && body.deliveries.every((row) => row.delivery_status === "PENDING" && Number(row.metadata?.retry_count || 0) >= 1);
  }, (body) => ({ count: body.count, deliveries: body.deliveries }));

  const acknowledgedApi = await apiFetch(`/api/v1/broadcasts/${campaignId}/deliveries?status=ACKNOWLEDGED&limit=100`);
  assertApi("acknowledged deliveries", acknowledgedApi, (body) => {
    return body.count === 1 && body.deliveries[0]?.farmer_id === selectedFarmerId && body.deliveries[0]?.delivery_status === "ACKNOWLEDGED";
  }, (body) => ({ count: body.count, deliveries: body.deliveries }));

  const auditApi = await apiFetch(`/api/v1/broadcasts/${campaignId}/audit?limit=100`);
  assertApi("broadcast audit", auditApi, (body) => {
    const actions = new Set((body.events || []).map((row) => row.action));
    return actions.has("RETRY_DELIVERIES") && actions.has("MARK_DELIVERY_READ") && actions.has("ACKNOWLEDGE_DELIVERY");
  }, (body) => ({ count: body.count, actions: (body.events || []).map((row) => row.action) }));

  await page.goto(broadcastUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Broadcasts", exact: true }).waitFor({ timeout: 20000 });
  await applyFilters();
  await page.getByText("FPO project closure migration notice").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByRole("button", { name: "View" }).first().click();

  await page.getByRole("heading", { name: "Broadcast detail" }).waitFor({ timeout: 20000 });
  await page.getByText("Delivery lifecycle").waitFor({ timeout: 20000 });
  await page.getByText("Retried rows").waitFor({ timeout: 20000 });
  await page.getByText("Skipped ack/read").waitFor({ timeout: 20000 });
  await page.locator('xpath=//div[normalize-space()="Retried rows"]/following-sibling::*[1][normalize-space()="11"]').waitFor({ timeout: 20000 });
  await page.locator('xpath=//div[normalize-space()="Skipped ack/read"]/following-sibling::*[1][normalize-space()="1"]').waitFor({ timeout: 20000 });

  await page.getByLabel("Status").last().selectOption("PENDING");
  await page.getByRole("button", { name: "Load deliveries" }).click();
  await page.getByText("11 delivery row(s) returned.").waitFor({ timeout: 20000 });
  await page.getByText("PENDING").last().waitFor({ timeout: 20000 });

  await page.getByRole("button", { name: "Load audit" }).click();
  await page.getByText("audit event(s) returned").waitFor({ timeout: 20000 });
  await page.getByText("RETRY_DELIVERIES").waitFor({ timeout: 20000 });
  await page.getByText("MARK_DELIVERY_READ").waitFor({ timeout: 20000 });
  await page.getByText("ACKNOWLEDGE_DELIVERY").waitFor({ timeout: 20000 });

  const screenshotPath = path.join(screenshotDir, "broadcast-pending-followup.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "broadcast_pending_followup_web_smoke.v1",
    status: "PASSED",
    url: broadcastUrl,
    screenshot: screenshotPath,
    tenant_id: tenantId,
    actor_id: actorId,
    project_id: projectId,
    campaign_id: campaignId,
    evidence: {
      broadcast_pending_delivery_count: campaignApi.body.delivery_summary.pending,
      broadcast_acknowledged_delivery_count: campaignApi.body.delivery_summary.acknowledged,
      broadcast_retry_retried_rows: campaignApi.body.metadata.last_delivery_retry_retried,
      broadcast_retry_skipped_ack_read_rows: campaignApi.body.metadata.last_delivery_retry_skipped_acknowledged,
      broadcast_pending_drilldown_count: pendingApi.body.count,
      broadcast_retry_audit_visible: true,
      broadcast_read_ack_audit_still_visible: true,
    },
    api_cross_check_passed: true,
  }, null, 2));
} catch (error) {
  const screenshotPath = path.join(screenshotDir, "broadcast-pending-followup-failure.png");
  try {
    await page.screenshot({ path: screenshotPath, fullPage: true });
  } catch {
    // Best effort only.
  }
  console.error(JSON.stringify({
    schema_version: "broadcast_pending_followup_web_smoke_failure.v1",
    status: "FAILED",
    screenshot: screenshotPath,
    message: error instanceof Error ? error.message : String(error),
    body_text_sample: (await page.locator("body").innerText().catch(() => "")).slice(0, 5000),
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}