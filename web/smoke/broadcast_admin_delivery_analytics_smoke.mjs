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
const selectedMobile = process.env.FPO_SELECTED_MOBILE || "+919900002106";
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

// Establish the web app origin before browser-side API probes. Fetching from
// about:blank can fail as an origin-less browser request even when backend is up.
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
    throw new Error(`${label} API predicate failed: ${JSON.stringify(detailBuilder(response.body)).slice(0, 1500)}`);
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
    return body.status === "PUBLISHED"
      && body.project_id === projectId
      && summary.total === 12
      && summary.acknowledged >= 1
      && summary.read >= 1;
  }, (body) => ({ status: body.status, project_id: body.project_id, delivery_summary: body.delivery_summary, metadata: body.metadata }));

  const deliveriesApi = await apiFetch(`/api/v1/broadcasts/${campaignId}/deliveries?status=ACKNOWLEDGED&limit=100`);
  assertApi("acknowledged deliveries", deliveriesApi, (body) => {
    return body.count >= 1 && body.deliveries.some((row) =>
      row.farmer_id === selectedFarmerId
      && row.delivery_status === "ACKNOWLEDGED"
      && row.read_at
      && row.acknowledged_at
    );
  }, (body) => ({ count: body.count, deliveries: body.deliveries }));

  const auditApi = await apiFetch(`/api/v1/broadcasts/${campaignId}/audit?limit=100`);
  assertApi("broadcast audit", auditApi, (body) => {
    const actions = new Set((body.events || []).map((row) => row.action));
    return actions.has("MARK_DELIVERY_READ") && actions.has("ACKNOWLEDGE_DELIVERY");
  }, (body) => ({ count: body.count, actions: (body.events || []).map((row) => row.action) }));

  await page.goto(broadcastUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Broadcasts", exact: true }).waitFor({ timeout: 20000 });
  await applyFilters();
  await page.getByText("FPO project closure migration notice").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText(campaignId).first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("PUBLISHED").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("12").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByRole("button", { name: "View" }).first().click();

  await page.getByRole("heading", { name: "Broadcast detail" }).waitFor({ timeout: 20000 });
  await page.getByText("Delivery lifecycle").waitFor({ timeout: 20000 });
  await page.locator('xpath=//h3[normalize-space()="Delivery lifecycle"]/following-sibling::div[1]//*[normalize-space()="Acknowledged"]').first().waitFor({ timeout: 20000 });
  await page.getByText("Targeted farmers").waitFor({ timeout: 20000 });
  await page.getByText("Created rows").waitFor({ timeout: 20000 });

  await page.getByLabel("Status").last().selectOption("ACKNOWLEDGED");
  await page.getByRole("button", { name: "Load deliveries" }).click();
  await page.getByText("delivery row(s) returned").waitFor({ timeout: 20000 });
  await page.getByText("FPO Farmer 06 Maize").waitFor({ timeout: 20000 });
  await page.getByText(selectedMobile).waitFor({ timeout: 20000 });
  await page.getByText("ACKNOWLEDGED").last().waitFor({ timeout: 20000 });

  await page.getByRole("button", { name: "Load audit" }).click();
  await page.getByText("audit event(s) returned").waitFor({ timeout: 20000 });
  await page.getByText("MARK_DELIVERY_READ").waitFor({ timeout: 20000 });
  await page.getByText("ACKNOWLEDGE_DELIVERY").waitFor({ timeout: 20000 });

  const screenshotPath = path.join(screenshotDir, "broadcast-admin-delivery-analytics.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "broadcast_admin_delivery_analytics_web_smoke.v1",
    status: "PASSED",
    url: broadcastUrl,
    screenshot: screenshotPath,
    tenant_id: tenantId,
    actor_id: actorId,
    project_id: projectId,
    campaign_id: campaignId,
    selected_farmer_id: selectedFarmerId,
    evidence: {
      broadcast_admin_campaign_visible: true,
      broadcast_admin_delivery_total: campaignApi.body.delivery_summary.total,
      broadcast_admin_read_count: campaignApi.body.delivery_summary.read,
      broadcast_admin_acknowledged_count: campaignApi.body.delivery_summary.acknowledged,
      broadcast_admin_ack_drilldown_selected_farmer_visible: true,
      broadcast_admin_audit_mark_read_visible: true,
      broadcast_admin_audit_acknowledge_visible: true,
    },
    api_cross_check_passed: true,
  }, null, 2));
} catch (error) {
  const screenshotPath = path.join(screenshotDir, "broadcast-admin-delivery-analytics-failure.png");
  try {
    await page.screenshot({ path: screenshotPath, fullPage: true });
  } catch {
    // Best effort only.
  }
  console.error(JSON.stringify({
    schema_version: "broadcast_admin_delivery_analytics_web_smoke_failure.v1",
    status: "FAILED",
    screenshot: screenshotPath,
    message: error instanceof Error ? error.message : String(error),
    body_text_sample: (await page.locator("body").innerText().catch(() => "")).slice(0, 5000),
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}