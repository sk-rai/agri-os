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
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });

await page.addInitScript(({ token, tenantId, actorId }) => {
  window.localStorage.setItem("agrios_token", token);
  window.localStorage.setItem("agrios_tenant_id", tenantId);
  window.localStorage.setItem("agrios_user_id", actorId);
}, { token, tenantId, actorId });

await page.goto(`${baseUrl}/core-lgd-review`, { waitUntil: "networkidle" });

await page.getByRole("heading", { name: "CoRE / LGD Mapping Review" }).waitFor({ timeout: 15000 });
await page.getByText("This surface is read-only").waitFor({ timeout: 15000 });
await page.getByText("POLY_REV").waitFor({ timeout: 15000 });
await page.getByText("Behavior changed").waitFor({ timeout: 15000 });
await page.getByRole("heading", { name: "Review rows" }).waitFor({ timeout: 15000 });
await page.getByRole("heading", { name: "Review rows" }).waitFor({ timeout: 15000 });
await page.getByText("CoRE candidate").first().waitFor({ timeout: 15000 });
await page.waitForFunction(() => {
  const text = document.body.innerText;
  return text.includes("PILOT_REVIEW_REPLACES_FALLBACK")
    && text.includes("Fallback")
    && text.includes("CoRE candidate")
    && !text.includes("Role FARMER does not grant VIEW");
}, null, { timeout: 15000 });

const errorBanner = page.locator("text=does not grant VIEW");
if (await errorBanner.count()) {
  throw new Error("Page still has permission denied banner; smoke session is not admin.");
}

await page.screenshot({
  path: `${screenshotDir}/core-lgd-review.png`,
  fullPage: true,
});

await page.waitForFunction(() => {
  const text = document.body.innerText;
  return !text.includes("Loading review rows") && !text.includes("Role FARMER does not grant VIEW");
}, null, { timeout: 15000 });

const rows = await page.locator("tbody tr").count();

console.log(JSON.stringify({
  schema_version: "core_lgd_review_web_smoke.v1",
  status: "PASSED",
  url: `${baseUrl}/core-lgd-review`,
  screenshot: path.join(screenshotDir, "core-lgd-review.png"),
  tenant_id: tenantId,
  rows_seen: rows,
}, null, 2));

await browser.close();
