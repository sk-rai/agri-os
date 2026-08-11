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
const screenUrl = process.env.WEB_LAND_SUMMARY_URL || `${baseUrl}/land-intelligence-summary`;
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });

await page.addInitScript(({ token, tenantId, actorId }) => {
  window.localStorage.setItem("agrios_token", token);
  window.localStorage.setItem("agrios_tenant_id", tenantId);
  window.localStorage.setItem("agrios_user_id", actorId);
  window.localStorage.setItem("agrios_role", "ENTERPRISE_ADMIN");
}, { token, tenantId, actorId });

const cleanupOverrideIds = [];

async function apiFetch(pathname, options = {}) {
  return await page.evaluate(
    async ({ apiBaseUrl, pathname, token, tenantId, actorId, options }) => {
      const response = await fetch(`${apiBaseUrl}${pathname}`, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Tenant-ID": tenantId,
          "X-Actor-ID": actorId,
          ...(options.headers || {}),
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
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
    { apiBaseUrl, pathname, token, tenantId, actorId, options }
  );
}

try {
  await page.goto(screenUrl, { waitUntil: "networkidle" });

  await page.getByRole("heading", { name: "Land intelligence summary", level: 1 }).waitFor({ timeout: 20000 });
  await page.getByText("Configure simple informational").waitFor({ timeout: 15000 });
  await page.getByText("Android contract: informational only").waitFor({ timeout: 15000 });

  const alreadyDefault = await page.getByText("DEFAULT_GENERATED").first().isVisible().catch(() => false);
  if (!alreadyDefault && await page.getByText("TENANT_OVERRIDE").first().isVisible().catch(() => false)) {
    const deactivateButton = page.getByRole("button", { name: "Deactivate effective summary" });
    if (await deactivateButton.isEnabled().catch(() => false)) {
      await deactivateButton.click();
      await page.waitForFunction(() => document.body.innerText.includes("DEFAULT_GENERATED"), null, { timeout: 20000 });
    }
  }

  await page.getByText("DEFAULT_GENERATED").first().waitFor({ timeout: 15000 });

  const title = `Playwright land summary ${Math.random().toString(16).slice(2, 10)}`;
  const overridePayload = {
    title: { en: title },
    subtitle: { en: "Playwright reviewed local guidance" },
    cards: [
      {
        key: "region",
        title: { en: "Region" },
        value: { en: "PIN 560001 smoke" },
        detail: { en: "Browser smoke editable company summary." },
      },
      {
        key: "soil_water",
        title: { en: "Soil & water" },
        value: { en: "Check irrigation" },
        detail: { en: "Ask farmer about water availability." },
      },
    ],
    main_crops: [
      { crop_code: "RICE", label: { en: "Rice" }, reason: { en: "Project-preferred crop." } },
    ],
    alternate_crops: [
      { crop_code: "MAIZE", label: { en: "Maize" }, reason: { en: "Backup option." } },
    ],
    caveats: [
      { en: "This remains informational and should not block onboarding." },
    ],
    version: "playwright-v1",
  };

  await page.locator("textarea").first().waitFor({ timeout: 15000 });
  await page.locator("textarea").first().fill(JSON.stringify(overridePayload, null, 2));
  await page.getByLabel("Review notes").fill("Playwright land summary smoke");
  await page.getByLabel("Reason").fill("Playwright land summary smoke");
  await page.getByRole("button", { name: "Save published summary" }).click();

  await page.waitForFunction(() => document.body.innerText.includes("TENANT_OVERRIDE") || document.body.innerText.includes("Failed to save"), null, { timeout: 20000 });
  const afterSaveText = await page.locator("body").innerText();
  if (afterSaveText.includes("Failed to save")) {
    throw new Error(`UI save showed failure: ${afterSaveText.slice(0, 2000)}`);
  }
  await page.getByText("TENANT_OVERRIDE").first().waitFor({ timeout: 15000 });
  await page.getByText(title).first().waitFor({ timeout: 15000 });

  const apiAfterSave = await apiFetch("/api/v1/admin/land-intelligence-summaries/effective?scope_type=PIN&scope_code=560001&language_code=en&season_code=KHARIF&crop_code=RICE");
  if (apiAfterSave.status !== 200) {
    throw new Error(`Admin effective API failed after UI save: ${apiAfterSave.status}`);
  }
  if (apiAfterSave.body.summary_source !== "TENANT_OVERRIDE" || apiAfterSave.body.summary_payload.title.en !== title) {
    throw new Error(`Saved land summary not effective via API: ${JSON.stringify(apiAfterSave.body)}`);
  }
  cleanupOverrideIds.push(apiAfterSave.body.effective_override?.id);

  const runtimeAfterSave = await apiFetch("/api/v1/profile/land-intelligence-summary?pin_code=560001&language_code=en&season_code=KHARIF&crop_code=RICE");
  if (runtimeAfterSave.status !== 200) {
    throw new Error(`Runtime summary API failed after UI save: ${runtimeAfterSave.status}`);
  }
  if (runtimeAfterSave.body.summary_source !== "TENANT_OVERRIDE" || runtimeAfterSave.body.summary_payload.title.en !== title) {
    throw new Error(`Runtime summary did not receive override: ${JSON.stringify(runtimeAfterSave.body)}`);
  }

  await page.getByRole("button", { name: "Deactivate effective summary" }).click();
  await page.waitForFunction(() => document.body.innerText.includes("DEFAULT_GENERATED"), null, { timeout: 20000 });
  await page.getByText("DEFAULT_GENERATED").first().waitFor({ timeout: 15000 });

  const apiAfterDeactivate = await apiFetch("/api/v1/admin/land-intelligence-summaries/effective?scope_type=PIN&scope_code=560001&language_code=en&season_code=KHARIF&crop_code=RICE");
  if (apiAfterDeactivate.status !== 200) {
    throw new Error(`Admin effective API failed after deactivate: ${apiAfterDeactivate.status}`);
  }
  if (apiAfterDeactivate.body.summary_source !== "DEFAULT_GENERATED") {
    throw new Error(`Fallback not restored after UI deactivate: ${JSON.stringify(apiAfterDeactivate.body)}`);
  }

  const screenshotPath = path.join(screenshotDir, "land-intelligence-summary-admin.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "land_intelligence_summary_web_smoke.v1",
    status: "PASSED",
    url: screenUrl,
    screenshot: screenshotPath,
    tenant_id: tenantId,
    actor_id: actorId,
    scope_type: "PIN",
    scope_code: "560001",
    override_lifecycle: "DEFAULT_GENERATED -> TENANT_OVERRIDE -> DEFAULT_GENERATED",
    runtime_api_cross_check_passed: true,
  }, null, 2));
} catch (error) {
  const failureScreenshot = path.join(screenshotDir, "land-intelligence-summary-admin-failure.png");
  await page.screenshot({ path: failureScreenshot, fullPage: true });
  const bodyText = await page.locator("body").innerText().catch(() => "BODY_TEXT_UNAVAILABLE");
  console.error(JSON.stringify({
    schema_version: "land_intelligence_summary_web_smoke_failure.v1",
    status: "FAILED",
    screenshot: failureScreenshot,
    message: error instanceof Error ? error.message : String(error),
    body_text_sample: bodyText.slice(0, 3000),
  }, null, 2));
  throw error;
} finally {
  for (const overrideId of cleanupOverrideIds.filter(Boolean)) {
    try {
      await apiFetch(`/api/v1/admin/land-intelligence-summaries/overrides/${overrideId}`, {
        method: "DELETE",
        body: { reason: "Playwright land summary smoke cleanup fallback" },
      });
    } catch {
      // Best-effort cleanup only; normal UI path already deactivates.
    }
  }
  await browser.close();
}
