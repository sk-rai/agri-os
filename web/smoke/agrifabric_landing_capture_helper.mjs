import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const tab = (process.env.AGRIFABRIC_TAB || "overview").toLowerCase();
const viewportName = (process.env.AGRIFABRIC_VIEWPORT || "desktop").toLowerCase();
const outputName = process.env.AGRIFABRIC_OUTPUT || `agrifabric-${tab}-${viewportName}.png`;
const fullPageOverride = String(process.env.AGRIFABRIC_FULL_PAGE || "").toLowerCase() === "true";

const tabLabels = {
  overview: "Overview",
  product: "Product",
  graph: "Evidence graph",
  operations: "Operations",
  geography: "Geography",
  roadmap: "Roadmap",
};

const viewports = {
  desktop: { width: 1440, height: 1100 },
  thumbnail: { width: 1280, height: 720 },
  square: { width: 1080, height: 1080 },
  mobile: { width: 390, height: 900 },
};

if (!tabLabels[tab]) {
  throw new Error(`Unknown AGRIFABRIC_TAB=${tab}. Use one of: ${Object.keys(tabLabels).join(", ")}`);
}

if (!viewports[viewportName]) {
  throw new Error(`Unknown AGRIFABRIC_VIEWPORT=${viewportName}. Use one of: ${Object.keys(viewports).join(", ")}`);
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots", "agrifabric");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: viewports[viewportName] });

async function clickTab(label) {
  const tabStrip = page.locator("div").filter({ hasText: "START HERE" }).filter({ hasText: "BOUNDARIES" }).first();
  await tabStrip.getByRole("button", { name: new RegExp(label, "i") }).click();
}

try {
  await page.goto(`${baseUrl}/agrifabric`, { waitUntil: "networkidle" });
  await page.getByText("AgriFabric").first().waitFor({ timeout: 20000 });

  if (tab !== "overview") {
    await clickTab(tabLabels[tab]);
  }

  await page.waitForTimeout(500);

  const outputPath = path.join(screenshotDir, outputName);
  await page.screenshot({ path: outputPath, fullPage: fullPageOverride || viewportName === "desktop" || viewportName === "mobile" });

  console.log(JSON.stringify({
    schema_version: "agrifabric_landing_capture_helper.v1",
    status: "PASSED",
    url: `${baseUrl}/agrifabric`,
    tab,
    tab_label: tabLabels[tab],
    viewport: viewportName,
    full_page: fullPageOverride || viewportName === "desktop" || viewportName === "mobile",
    output: outputPath,
  }, null, 2));
} finally {
  await browser.close();
}
