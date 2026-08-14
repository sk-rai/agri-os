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
const fieldEventId = process.env.FIELD_EVENT_ADVISORY_EVENT_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002994";
const mediaAssetId = process.env.FIELD_EVENT_ADVISORY_MEDIA_ASSET_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002995";
const campaignId = process.env.FIELD_EVENT_ADVISORY_CAMPAIGN_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002996";
const includedFarmerId = process.env.FIELD_EVENT_ADVISORY_INCLUDED_FARMER_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002106";
const excludedFarmerId = process.env.FIELD_EVENT_ADVISORY_EXCLUDED_FARMER_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002101";
const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const fieldEventsUrl = `${baseUrl}/field-events`;
const broadcastsUrl = `${baseUrl}/broadcasts`;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const expected = {
  eventType: "PEST",
  severity: "HIGH",
  eventStatus: "ADVISORY_SENT",
  campaignTitle: "Field event pest advisory broadcast",
  contentTitle: "Maize pest photo advisory",
  mediaCaption: "Source field event pest photo",
  storageUrl: "https://static.example.test/agrios/smoke/fpo-field-event-pest-photo.jpg",
  mediaTypeMime: "PHOTO / image/jpeg",
  contract: "field_event_advisory_loop.v1",
};

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1680, height: 1400 } });

await page.addInitScript(({ token, tenantId, actorId }) => {
  window.localStorage.setItem("agrios_token", token);
  window.localStorage.setItem("agrios_tenant_id", tenantId);
  window.localStorage.setItem("agrios_user_id", actorId);
  window.localStorage.setItem("agrios_role", "ENTERPRISE_ADMIN");
}, { token, tenantId, actorId });

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

async function waitForBodyText(text, timeout = 20000) {
  await page.waitForFunction(
    (needle) => document.body.innerText.includes(needle),
    text,
    { timeout }
  );
}

function feedItemForCampaign(feedBody) {
  return (feedBody.broadcasts || []).find((row) => row.campaign?.id === campaignId);
}

try {
  await page.goto(fieldEventsUrl, { waitUntil: "domcontentloaded" });

  const eventApi = await apiFetch(`/api/v1/field-events/${fieldEventId}`);
  assertApi("field event detail", eventApi, (body) => {
    const media = body.media_attachments || [];
    return body.id === fieldEventId
      && body.status === expected.eventStatus
      && body.event_type === expected.eventType
      && body.severity === expected.severity
      && body.metadata?.advisory_campaign_id === campaignId
      && media.length === 1
      && (media[0].media_asset_id === mediaAssetId || media[0].asset?.id === mediaAssetId)
      && media[0].purpose === "DISEASE_PHOTO";
  }, (body) => ({ status: body.status, event_type: body.event_type, severity: body.severity, metadata: body.metadata, media_attachments: body.media_attachments }));

  const campaignApi = await apiFetch(`/api/v1/broadcasts/${campaignId}`);
  assertApi("advisory campaign detail", campaignApi, (body) => {
    const media = body.contents?.[0]?.media_attachments || [];
    return body.status === "PUBLISHED"
      && body.project_id === projectId
      && body.metadata?.android_contract === expected.contract
      && body.metadata?.source_field_event_id === fieldEventId
      && body.metadata?.source_media_asset_id === mediaAssetId
      && body.delivery_summary?.total === 2
      && media.length === 1
      && media[0].id === mediaAssetId
      && media[0].attachment?.purpose === "ADVISORY_ATTACHMENT";
  }, (body) => ({ status: body.status, metadata: body.metadata, delivery_summary: body.delivery_summary, contents: body.contents }));

  const includedFeedApi = await apiFetch(`/api/v1/broadcasts/farmers/${includedFarmerId}/broadcasts?language_code=en&include_read=true`);
  assertApi("included farmer feed", includedFeedApi, (body) => {
    const item = feedItemForCampaign(body);
    const media = item?.content?.media_attachments || [];
    return item?.campaign?.metadata?.source_field_event_id === fieldEventId
      && item.content.title === expected.contentTitle
      && media.length === 1
      && media[0].id === mediaAssetId;
  }, (body) => ({ count: body.count, broadcasts: body.broadcasts }));

  const excludedFeedApi = await apiFetch(`/api/v1/broadcasts/farmers/${excludedFarmerId}/broadcasts?language_code=en&include_read=true`);
  assertApi("excluded farmer feed", excludedFeedApi, (body) => !feedItemForCampaign(body), (body) => ({ count: body.count, broadcasts: body.broadcasts }));

  await page.goto(fieldEventsUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Field Events", exact: true }).waitFor({ timeout: 20000 });
  await page.getByLabel("Project ID").fill(projectId);
  await page.getByLabel("Event type").selectOption(expected.eventType);
  await page.getByLabel("Severity").selectOption(expected.severity);
  await page.getByLabel("Status").selectOption(expected.eventStatus);
  await page.getByRole("button", { name: "Apply filters" }).click();
  await waitForBodyText(includedFarmerId);
  await waitForBodyText(expected.eventType);
  await waitForBodyText(expected.severity);
  await waitForBodyText(expected.eventStatus);
  await page.locator("tbody").getByRole("button", { name: "View" }).first().click();
  await waitForBodyText("Event detail");
  await waitForBodyText(fieldEventId);
  await waitForBodyText("Media attachments");
  await waitForBodyText("DISEASE_PHOTO - PHOTO - UPLOADED");
  await waitForBodyText(mediaAssetId);

  await page.goto(broadcastsUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Broadcasts", exact: true }).waitFor({ timeout: 20000 });
  await page.getByLabel("Project ID").fill(projectId);
  await page.getByLabel("Status").selectOption("PUBLISHED");
  await page.getByLabel("Category").last().selectOption("ADVISORY");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await waitForBodyText(expected.campaignTitle);
  await waitForBodyText(campaignId);
  await page.locator("tbody").getByRole("button", { name: "View" }).first().click();
  await waitForBodyText("Broadcast detail");
  await waitForBodyText(`en: ${expected.contentTitle}`);
  await waitForBodyText("Media attachments");
  await waitForBodyText(expected.mediaTypeMime);
  await waitForBodyText(expected.mediaCaption);
  await waitForBodyText(expected.storageUrl);

  const includedItem = feedItemForCampaign(includedFeedApi.body);
  const screenshotPath = path.join(screenshotDir, "field-event-advisory-loop.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "field_event_advisory_loop_web_smoke.v1",
    status: "PASSED",
    field_events_url: fieldEventsUrl,
    broadcasts_url: broadcastsUrl,
    screenshot: screenshotPath,
    tenant_id: tenantId,
    actor_id: actorId,
    project_id: projectId,
    field_event_id: fieldEventId,
    campaign_id: campaignId,
    media_asset_id: mediaAssetId,
    included_farmer_id: includedFarmerId,
    excluded_farmer_id: excludedFarmerId,
    evidence: {
      field_event_advisory_field_event_visible: true,
      field_event_advisory_status: eventApi.body.status,
      field_event_advisory_type: eventApi.body.event_type,
      field_event_advisory_source_media_asset_reused: campaignApi.body.contents[0].media_attachments[0].id === mediaAssetId,
      field_event_advisory_broadcast_visible: true,
      field_event_advisory_delivery_count: campaignApi.body.delivery_summary.total,
      field_event_advisory_included_farmer_visible: Boolean(includedItem),
      field_event_advisory_excluded_farmer_visible: Boolean(feedItemForCampaign(excludedFeedApi.body)),
      field_event_advisory_android_contract: campaignApi.body.metadata.android_contract,
      field_event_advisory_media_type: includedItem.content.media_attachments[0].media_type,
      field_event_advisory_attachment_purpose: includedItem.content.media_attachments[0].attachment.purpose,
    },
    api_cross_check_passed: true,
  }, null, 2));
} catch (error) {
  const screenshotPath = path.join(screenshotDir, "field-event-advisory-loop-failure.png");
  try {
    await page.screenshot({ path: screenshotPath, fullPage: true });
  } catch {
    // Best effort only.
  }
  console.error(JSON.stringify({
    schema_version: "field_event_advisory_loop_web_smoke_failure.v1",
    status: "FAILED",
    screenshot: screenshotPath,
    message: error instanceof Error ? error.message : String(error),
    body_text_sample: (await page.locator("body").innerText().catch(() => "")).slice(0, 5000),
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}
