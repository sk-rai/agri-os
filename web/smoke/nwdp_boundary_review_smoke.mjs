import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const token = process.env.WEB_SWEEP_TOKEN;
const tenantId = process.env.WEB_SWEEP_TENANT_ID || "default";
const actorId = process.env.WEB_SWEEP_ACTOR_ID;

if (!token || !actorId) {
  console.error("Missing WEB_SWEEP_TOKEN / WEB_SWEEP_ACTOR_ID. Generate them with create_web_ui_smoke_session.py.");
  process.exit(1);
}

const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const reviewUrl = process.env.WEB_NWDP_BOUNDARY_REVIEW_URL || `${baseUrl}/nwdp-boundary-review`;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
const browserEvents = [];

page.on("console", (message) => {
  browserEvents.push({ type: "console", level: message.type(), text: message.text() });
});

page.on("response", async (response) => {
  const url = response.url();
  if (url.includes("/nwdp-boundary-")) {
    browserEvents.push({
      type: "response",
      status: response.status(),
      url,
      text: (await response.text().catch(() => "")).slice(0, 1200),
    });
  }
});

page.on("pageerror", (error) => {
  browserEvents.push({ type: "pageerror", text: error.message });
});

await page.addInitScript(({ token, tenantId, actorId }) => {
  window.localStorage.setItem("agrios_token", token);
  window.localStorage.setItem("agrios_tenant_id", tenantId);
  window.localStorage.setItem("agrios_user_id", actorId);
}, { token, tenantId, actorId });

await page.goto(reviewUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
await page.waitForTimeout(3000);

try {
  await page.getByRole("heading", { name: "NWDP Boundary Review" }).waitFor({ timeout: 30000 });
} catch (error) {
  const bodyText = await page.locator("body").innerText().catch(() => "");
  await page.screenshot({
    path: `${screenshotDir}/nwdp-boundary-review-heading-failed.png`,
    fullPage: true,
  });
  throw new Error(`NWDP heading not visible. Current URL: ${page.url()}. Browser events: ${JSON.stringify(browserEvents, null, 2)} Page text excerpt: ${bodyText.slice(0, 3000)}`);
}
await page.getByText("Runtime matching: disabled").waitFor({ timeout: 15000 });
await page.getByText("Governance fence").waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Unresolved parent scope" }).waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Parent mismatch" }).waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Name-match review" }).waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Special/reference" }).waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Direct code candidates" }).waitFor({ timeout: 15000 });
await page.getByRole("heading", { name: "Candidates" }).waitFor({ timeout: 15000 });
await page.getByRole("heading", { name: "Selected candidate" }).waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Keep pending" }).waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Reference only" }).waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Reject mismatch" }).waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Block review" }).waitFor({ timeout: 15000 });
await page.getByText("Notes are required for non-pending decisions").waitFor({ timeout: 15000 });

await page.getByRole("button", { name: "Reference only" }).click();
await page.getByText("Reference-only is intended for special/reference features").waitFor({ timeout: 15000 });

await page.waitForFunction(() => {
  const text = document.body.innerText;
  return text.includes("PARENT_MATCH_VILLAGE_UNRESOLVED")
    && text.includes("MANUAL_REVIEW")
    && text.includes("Active / promoted")
    && !text.includes("Role FARMER does not grant VIEW");
}, null, { timeout: 15000 });

const errorBanner = page.locator("text=does not grant VIEW");
if (await errorBanner.count()) {
  throw new Error("Page still has permission denied banner; smoke session is not admin.");
}

await page.screenshot({
  path: `${screenshotDir}/nwdp-boundary-review.png`,
  fullPage: true,
});

let rows = 0;
for (let attempt = 0; attempt < 30; attempt += 1) {
  rows = await page.locator("tbody tr").count();
  if (rows > 0) break;
  await page.waitForTimeout(1000);
}

await page.getByText("Source codes").waitFor({ timeout: 15000 });
await page.getByText("Source names").waitFor({ timeout: 15000 });
await page.getByText("Source feature").waitFor({ timeout: 15000 });
await page.getByText("Review history").waitFor({ timeout: 15000 });

await page.getByRole("button", { name: "Direct code candidates" }).click();
await page.waitForFunction(() => {
  const text = document.body.innerText;
  return text.includes("DIRECT_VLCODE_MATCH") && text.includes("AUTO_CANDIDATE");
}, null, { timeout: 15000 });

await page.locator("tbody tr button").first().click();
await page.waitForTimeout(1000);
const matchEvidenceVisible = (await page.locator("body").innerText()).includes("Match evidence");

if (rows <= 0) {
  const bodyText = await page.locator("body").innerText();
  await page.screenshot({
    path: `${screenshotDir}/nwdp-boundary-review-failed.png`,
    fullPage: true,
  });
  throw new Error(`NWDP boundary review table did not render any candidate rows. Browser events: ${JSON.stringify(browserEvents, null, 2)} Page text excerpt: ${bodyText.slice(0, 5000)}`);
}

console.log(JSON.stringify({
  schema_version: "nwdp_boundary_review_web_smoke.v1",
  status: "PASSED",
  url: reviewUrl,
  screenshot: path.join(screenshotDir, "nwdp-boundary-review.png"),
  tenant_id: tenantId,
  rows_seen: rows,
  match_evidence_panel_seen: matchEvidenceVisible,
  runtime_spatial_matching_expected: "disabled",
}, null, 2));

await browser.close();
