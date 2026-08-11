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
const localizationUrl = process.env.WEB_LOCALIZATION_URL || `${baseUrl}/localization`;
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
  const response = await page.evaluate(
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
  return response;
}

try {
  await page.goto(localizationUrl, { waitUntil: "networkidle" });

  await page.getByRole("heading", { name: "Localization" }).waitFor({ timeout: 20000 });
  await page.getByText("Manage tenant/project language overrides").waitFor({ timeout: 15000 });
  await page.getByText("Content keys").first().waitFor({ timeout: 15000 });
  await page.getByText("Active overrides").first().waitFor({ timeout: 15000 });

  const permissionDenied = page.locator("text=ADMIN_PERMISSION_DENIED");
  if (await permissionDenied.count()) {
    throw new Error("Page has admin permission denied banner; smoke session is not admin.");
  }

  const languageSelect = page.getByLabel("Language");
  await languageSelect.selectOption("kn");

  const searchInput = page.getByLabel("Search");
  await searchInput.fill("activity_log.title");
  await page.getByRole("button", { name: "Search" }).click();

  await page.getByText("profile_form.activity_log.title").waitFor({ timeout: 15000 });
  await page.getByText("EN_FALLBACK").first().waitFor({ timeout: 15000 });
  await page.getByText("Log Activity").first().waitFor({ timeout: 15000 });

  await page.getByText("profile_form.activity_log.title").click();
  await page.getByRole("heading", { name: "Edit override" }).waitFor({ timeout: 15000 });
  await page.getByText("Effective source").waitFor({ timeout: 15000 });

  const overrideText = `Kannada UI override ${Math.random().toString(16).slice(2, 10)}`;
  await page.getByLabel("Override text (kn)").fill(overrideText);
  await page.getByLabel("Review notes").fill("Playwright admin localization smoke");
  await page.getByLabel("Reason").fill("Playwright admin localization smoke");
  await page.getByRole("button", { name: "Save published override" }).click();

  await page.getByText("Override created for profile_form.activity_log.title").waitFor({ timeout: 20000 });
  await page.getByText("TENANT_OVERRIDE").first().waitFor({ timeout: 15000 });
  await page.getByText(overrideText).first().waitFor({ timeout: 15000 });

  const listingAfterSave = await apiFetch("/api/v1/admin/localization/content-keys?language_code=kn&q=activity_log.title&include_overrides=true&limit=10");
  if (listingAfterSave.status !== 200) {
    throw new Error(`API listing after UI save failed: ${listingAfterSave.status}`);
  }
  const savedKey = listingAfterSave.body.content_keys[0];
  if (savedKey.effective.text !== overrideText || savedKey.effective.source !== "TENANT_OVERRIDE") {
    throw new Error(`Saved override was not effective via API: ${JSON.stringify(savedKey.effective)}`);
  }
  cleanupOverrideIds.push(savedKey.effective.override_id);

  await page.getByRole("button", { name: "Deactivate effective override" }).click();
  await page.getByText("Override deactivated for profile_form.activity_log.title").waitFor({ timeout: 20000 });
  await page.getByText("EN_FALLBACK").first().waitFor({ timeout: 15000 });

  const listingAfterDeactivate = await apiFetch("/api/v1/admin/localization/content-keys?language_code=kn&q=activity_log.title&include_overrides=true&limit=10");
  if (listingAfterDeactivate.status !== 200) {
    throw new Error(`API listing after UI deactivate failed: ${listingAfterDeactivate.status}`);
  }
  const finalKey = listingAfterDeactivate.body.content_keys[0];
  if (finalKey.effective.source !== "EN_FALLBACK" || finalKey.effective.text !== "Log Activity") {
    throw new Error(`Fallback not restored after UI deactivate: ${JSON.stringify(finalKey.effective)}`);
  }

  const screenshotPath = path.join(screenshotDir, "localization-admin.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "admin_localization_web_smoke.v1",
    status: "PASSED",
    url: localizationUrl,
    screenshot: screenshotPath,
    tenant_id: tenantId,
    actor_id: actorId,
    content_key: "profile_form.activity_log.title",
    override_lifecycle: "EN_FALLBACK -> TENANT_OVERRIDE -> EN_FALLBACK",
    api_cross_check_passed: true,
  }, null, 2));
} finally {
  for (const overrideId of cleanupOverrideIds.filter(Boolean)) {
    try {
      await apiFetch(`/api/v1/admin/localization/overrides/${overrideId}`, {
        method: "DELETE",
        body: { reason: "Playwright localization smoke cleanup fallback" },
      });
    } catch {
      // Best-effort cleanup only; normal UI path already deactivates.
    }
  }
  await browser.close();
}
