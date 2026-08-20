import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const landingUrl = `${baseUrl}/agrifabric`;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });

const requiredTabs = [
  "Overview",
  "Product",
  "Evidence graph",
  "Operations",
  "Geography",
  "Roadmap",
];

const requiredAssetPaths = [
  "/landing-assets/hero-composite.svg",
  "/landing-assets/hero-composite-compact.svg",
  "/landing-assets/product-pillars.svg",
  "/landing-assets/relationship-graph-overview.svg",
  "/landing-assets/field-evidence-pipeline.svg",
  "/landing-assets/geography-digipin-overview.svg",
  "/landing-assets/geography-global-extension-layer.svg",
  "/landing-assets/geography-digipin-layered-model.svg",
  "/landing-assets/insurance-risk-roadmap.svg",
  "/landing-assets/insurance-risk-roadmap-compact.svg",
];


async function clickTab(label) {
  const tabStrip = page.locator('div').filter({ hasText: 'START HERE' }).filter({ hasText: 'BOUNDARIES' }).first();
  await tabStrip.getByRole("button", { name: new RegExp(label, "i") }).click();
}

const evidence = {
  landing_loaded: false,
  tab_count: 0,
  overview_rendered: false,
  product_rendered: false,
  graph_rendered: false,
  operations_rendered: false,
  geography_rendered: false,
  roadmap_rendered: false,
  claim_boundary_visible: false,
  asset_count: 0,
  missing_assets: [],
  mobile_rendered: false,
};

try {
  await page.goto(landingUrl, { waitUntil: "networkidle" });

  await page.getByText("Offline-first field intelligence for agriculture programs.").waitFor({ timeout: 20000 });
  await page.getByText("Android MVP closed").waitFor({ timeout: 20000 });
  evidence.landing_loaded = true;
  evidence.overview_rendered = true;

  for (const tab of requiredTabs) {
    await page.getByRole("button", { name: new RegExp(tab, "i") }).first().waitFor({ timeout: 10000 });
  }
  evidence.tab_count = requiredTabs.length;

  await clickTab("Product");
  await page.getByText("Six verbs, one operating fabric.").waitFor({ timeout: 10000 });
  await page.getByText("Capture").first().waitFor({ timeout: 10000 });
  evidence.product_rendered = true;

  await clickTab("Evidence graph");
  await page.getByText("Every field interaction becomes a typed relationship.").waitFor({ timeout: 10000 });
  evidence.graph_rendered = true;

  await clickTab("Operations");
  await page.getByText("From field capture to governed operations.").waitFor({ timeout: 10000 });
  await page.getByText("Android onboarding").waitFor({ timeout: 10000 });
  evidence.operations_rendered = true;

  await clickTab("Geography");
  await page.getByText("PIN is context. GPS and DigiPin are precision evidence.").waitFor({ timeout: 10000 });
  evidence.geography_rendered = true;

  await clickTab("Roadmap");
  await page.getByText("Evidence foundation today. Review intelligence tomorrow.").waitFor({ timeout: 10000 });
  await page.getByText("Review-assistive, not auto-decisioning.").waitFor({ timeout: 10000 });
  evidence.roadmap_rendered = true;
  evidence.claim_boundary_visible = true;

  const assetStatuses = await page.evaluate(async (paths) => {
    const results = [];
    for (const assetPath of paths) {
      const response = await fetch(assetPath);
      results.push({ path: assetPath, status: response.status, ok: response.ok });
    }
    return results;
  }, requiredAssetPaths);

  evidence.asset_count = assetStatuses.filter((row) => row.ok).length;
  evidence.missing_assets = assetStatuses.filter((row) => !row.ok);

  if (evidence.missing_assets.length) {
    throw new Error(`Missing landing assets: ${JSON.stringify(evidence.missing_assets)}`);
  }

  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto(landingUrl, { waitUntil: "networkidle" });
  await page.getByText("Offline-first field intelligence for agriculture programs.").waitFor({ timeout: 10000 });
  await clickTab("Product");
  await page.getByText("Six verbs, one operating fabric.").waitFor({ timeout: 10000 });
  evidence.mobile_rendered = true;

  const screenshotPath = path.join(screenshotDir, "agrifabric-landing.png");
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(landingUrl, { waitUntil: "networkidle" });
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "agrifabric_landing_web_smoke.v1",
    status: "PASSED",
    url: landingUrl,
    screenshot: screenshotPath,
    evidence,
  }, null, 2));
} catch (error) {
  const screenshotPath = path.join(screenshotDir, "agrifabric-landing-failure.png");
  await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
  console.error(JSON.stringify({
    schema_version: "agrifabric_landing_web_smoke_failure.v1",
    status: "FAILED",
    url: landingUrl,
    screenshot: screenshotPath,
    message: error instanceof Error ? error.message : String(error),
    evidence,
    body_text_sample: (await page.locator("body").innerText().catch(() => "")).slice(0, 2000),
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}
