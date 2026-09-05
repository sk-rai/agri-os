import { chromium } from "playwright";

const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const url = `${baseUrl}/geography-layer-readiness`;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

const responses = [];
page.on("response", async (response) => {
  if (response.url().includes("/api/v1/master-data/geography/layer-readiness")) {
    responses.push({
      status: response.status(),
      url: response.url(),
      text: await response.text().catch(() => ""),
    });
  }
});

await page.goto(url, { waitUntil: "networkidle" });

await page.getByText("Geography layer readiness").first().waitFor({ timeout: 30000 });
await page.getByText("Cross-layer state and district matrix").waitFor({ timeout: 30000 });
await page.getByText("LGD villages").waitFor({ timeout: 30000 });
await page.getByText("Boundary outside matrix").waitFor({ timeout: 30000 });
await page.getByText("State/district readiness matrix").waitFor({ timeout: 30000 });

const bodyText = await page.locator("body").innerText();
for (const expected of [
  "LGD canonical runtime identity",
  "Village PIN-code lookup",
  "NWDP demographic Android-disabled",
  "NWDP boundary runtime-disabled",
  "SOI direct join blocked",
  "BharatAtlas review source",
]) {
  if (!bodyText.includes(expected)) {
    throw new Error(`Expected readiness posture text missing: ${expected}`);
  }
}

await page.screenshot({ path: "web/smoke/screenshots/geography-layer-readiness.png", fullPage: true });

console.log(JSON.stringify({
  schema_version: "geography_layer_readiness_web_smoke.v1",
  status: "PASSED",
  url,
  readiness_responses_seen: responses.length,
  screenshot: "web/smoke/screenshots/geography-layer-readiness.png",
}, null, 2));

await browser.close();
