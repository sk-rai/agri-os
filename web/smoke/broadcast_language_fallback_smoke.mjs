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
const campaignId = process.env.BROADCAST_LANGUAGE_CAMPAIGN_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002970";
const selectedFarmerId = process.env.FPO_SELECTED_FARMER_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002106";
const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const broadcastUrl = `${baseUrl}/broadcasts`;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const expected = {
  title: "FPO language fallback advisory smoke",
  enTitle: "Pest scouting language fallback advisory",
  hiTitle: "कीट फोटो सलाह",
  caption: "Fallback scouting reference photo",
  storageUrl: "https://static.example.test/agrios/smoke/fpo-language-fallback-photo.jpg",
  mediaTypeMime: "PHOTO / image/jpeg",
};

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

function findCampaignFeedItem(body) {
  return (body.broadcasts || []).find((row) => row.campaign?.id === campaignId);
}

try {
  const campaignApi = await apiFetch(`/api/v1/broadcasts/${campaignId}`);
  assertApi("campaign language detail", campaignApi, (body) => {
    const languages = new Set((body.contents || []).map((row) => row.language_code));
    return body.status === "PUBLISHED"
      && body.project_id === projectId
      && (body.delivery_summary || {}).total === 1
      && languages.has("en")
      && languages.has("hi");
  }, (body) => ({ status: body.status, project_id: body.project_id, delivery_summary: body.delivery_summary, contents: body.contents }));

  const hiFeedApi = await apiFetch(`/api/v1/broadcasts/farmers/${selectedFarmerId}/broadcasts?language_code=hi&include_read=true`);
  assertApi("hindi farmer feed", hiFeedApi, (body) => {
    const item = findCampaignFeedItem(body);
    return item?.content?.language_code === "hi" && item.content.title === expected.hiTitle;
  }, (body) => ({ count: body.count, broadcasts: body.broadcasts }));

  const fallbackFeedApi = await apiFetch(`/api/v1/broadcasts/farmers/${selectedFarmerId}/broadcasts?language_code=kn&include_read=true`);
  assertApi("fallback farmer feed", fallbackFeedApi, (body) => {
    const item = findCampaignFeedItem(body);
    const media = item?.content?.media_attachments || [];
    return item?.content?.language_code === "en"
      && item.content.title === expected.enTitle
      && media.length === 1
      && media[0].storage_url === expected.storageUrl
      && (media[0].attachment || {}).caption === expected.caption;
  }, (body) => ({ count: body.count, broadcasts: body.broadcasts }));

  await page.goto(broadcastUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Broadcasts", exact: true }).waitFor({ timeout: 20000 });
  await page.getByLabel("Project ID").fill(projectId);
  await page.getByLabel("Status").selectOption("PUBLISHED");
  await page.getByLabel("Category").last().selectOption("ADVISORY");
  await page.getByRole("button", { name: "Apply filters" }).click();

  await waitForBodyText(expected.title);
  await waitForBodyText(campaignId);
  await page.locator("tbody").getByRole("button", { name: "View" }).first().click();

  await waitForBodyText("Broadcast detail");
  await waitForBodyText(`en: ${expected.enTitle}`);
  await waitForBodyText(`hi: ${expected.hiTitle}`);
  await waitForBodyText("Media attachments");
  await waitForBodyText(expected.mediaTypeMime);
  await waitForBodyText(expected.caption);
  await waitForBodyText(expected.storageUrl);

  const fallbackItem = findCampaignFeedItem(fallbackFeedApi.body);
  const screenshotPath = path.join(screenshotDir, "broadcast-language-fallback.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "broadcast_language_fallback_web_smoke.v1",
    status: "PASSED",
    url: broadcastUrl,
    screenshot: screenshotPath,
    tenant_id: tenantId,
    actor_id: actorId,
    project_id: projectId,
    campaign_id: campaignId,
    selected_farmer_id: selectedFarmerId,
    evidence: {
      broadcast_language_campaign_visible: true,
      broadcast_language_delivery_total: campaignApi.body.delivery_summary.total,
      broadcast_language_content_codes: campaignApi.body.contents.map((row) => row.language_code).sort(),
      broadcast_language_hi_selected: findCampaignFeedItem(hiFeedApi.body).content.language_code === "hi",
      broadcast_language_unsupported_kn_fallback: fallbackItem.content.language_code === "en",
      broadcast_language_fallback_media_count: fallbackItem.content.media_attachments.length,
      broadcast_language_fallback_media_type: fallbackItem.content.media_attachments[0].media_type,
      broadcast_language_fallback_text_present: Boolean(fallbackItem.content.body_text),
      broadcast_language_selection_backend_owned: true,
    },
    api_cross_check_passed: true,
  }, null, 2));
} catch (error) {
  const screenshotPath = path.join(screenshotDir, "broadcast-language-fallback-failure.png");
  try {
    await page.screenshot({ path: screenshotPath, fullPage: true });
  } catch {
    // Best effort only.
  }
  console.error(JSON.stringify({
    schema_version: "broadcast_language_fallback_web_smoke_failure.v1",
    status: "FAILED",
    screenshot: screenshotPath,
    message: error instanceof Error ? error.message : String(error),
    body_text_sample: (await page.locator("body").innerText().catch(() => "")).slice(0, 5000),
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}