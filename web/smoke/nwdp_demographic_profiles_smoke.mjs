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
const screenUrl = process.env.WEB_NWDP_DEMOGRAPHIC_PROFILES_URL || `${baseUrl}/nwdp-demographic-profiles`;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const expectedPromotedVillages = [
  "Bambooflat CT",
  "Garacharma CT",
  "Hut Bay Rv",
  "Prothrapur CT",
  "Ramakrishnapur Rv",
];

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
const browserEvents = [];

page.on("console", (message) => {
  browserEvents.push({ type: "console", level: message.type(), text: message.text() });
});

page.on("response", async (response) => {
  const url = response.url();
  if (url.includes("/nwdp-demographic-profiles")) {
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
  window.localStorage.setItem("agrios_role", "ENTERPRISE_ADMIN");
}, { token, tenantId, actorId });

try {
  await page.goto(screenUrl, { waitUntil: "domcontentloaded", timeout: 45000 });

  await page.getByRole("heading", { name: "Promoted village demographics", level: 1 }).waitFor({ timeout: 30000 });
  await page.getByText("NWDP demographic profiles").first().waitFor({ timeout: 15000 });
  await page.getByText("Runtime lookup and Android behavior remain disabled").waitFor({ timeout: 15000 });

  await page.waitForFunction(() => {
    const text = document.body.innerText;
    return !text.includes("Loading demographic profiles…")
      && text.includes("Profiles")
      && text.includes("Active")
      && text.includes("Promoted")
      && text.includes("Auto candidates")
      && text.includes("Village profiles")
      && text.includes("Showing 1-100 of 780 matching profiles");
  }, null, { timeout: 30000 });

  await page.getByLabel("State / UT").selectOption("Andaman & Nicobar Island");
  await page.getByLabel("District").locator("option", { hasText: "South Andamans" }).waitFor({ state: "attached", timeout: 30000 });
  await page.getByLabel("District").selectOption("South Andamans");
  await page.getByRole("button", { name: "Refresh" }).click();
  await page.getByText("5 promoted profile rows shown").waitFor({ timeout: 30000 });

  const bodyText = await page.locator("body").innerText();
  for (const village of expectedPromotedVillages) {
    if (!bodyText.includes(village)) {
      throw new Error(`Expected promoted village was not visible: ${village}`);
    }
  }

  if (!bodyText.includes("APPROVED FOR PROMOTION") || !bodyText.includes("PROMOTED")) {
    throw new Error(`Promotion status badges were not visible. Page text excerpt: ${bodyText.slice(0, 3000)}`);
  }

  const initialRows = await page.locator("tbody tr").count();
  if (initialRows < expectedPromotedVillages.length) {
    throw new Error("Expected promoted profile rows before filtering, saw " + initialRows);
  }

  await page.getByPlaceholder("Search village").fill("Bambooflat");
  await page.getByRole("button", { name: "Refresh" }).click();
  await page.waitForFunction(() => {
    const text = document.body.innerText;
    return text.includes("Bambooflat CT") && text.includes("1 promoted profile rows shown");
  }, null, { timeout: 30000 });

  const rows = await page.locator("tbody tr").count();
  if (rows !== 1) {
    throw new Error("Expected exactly one Bambooflat profile row after filtering, saw " + rows);
  }

  const screenshotPath = path.join(screenshotDir, "nwdp-demographic-profiles.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "nwdp_demographic_profiles_web_smoke.v1",
    status: "PASSED",
    url: screenUrl,
    screenshot: screenshotPath,
    tenant_id: tenantId,
    actor_id: actorId,
    promoted_villages_seen: expectedPromotedVillages,
    initial_rows_seen: initialRows,
    filtered_rows_seen: rows,
    state_dropdown_checked: "Andaman & Nicobar Island",
    district_dropdown_checked: "South Andamans",
    village_name_filter_checked: "Bambooflat",
    runtime_lookup_expected: "disabled",
  }, null, 2));
} catch (error) {
  const failureScreenshot = path.join(screenshotDir, "nwdp-demographic-profiles-failure.png");
  await page.screenshot({ path: failureScreenshot, fullPage: true });
  const bodyText = await page.locator("body").innerText().catch(() => "BODY_TEXT_UNAVAILABLE");
  console.error(JSON.stringify({
    schema_version: "nwdp_demographic_profiles_web_smoke_failure.v1",
    status: "FAILED",
    screenshot: failureScreenshot,
    message: error instanceof Error ? error.message : String(error),
    browser_events: browserEvents,
    body_text_sample: bodyText.slice(0, 5000),
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}
