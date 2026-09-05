import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { chromium } from "playwright";

const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const url = `${baseUrl}/geography-layer-readiness`;
const tenantId = "default";
function pythonJson(code) {
  const stdout = execFileSync("../venv/bin/python", ["-c", code], {
    cwd: process.cwd(),
    encoding: "utf-8",
  });
  return JSON.parse(stdout);
}

const admin = pythonJson(`
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent / "backend"))
from app.core.database import SessionLocal
from scripts.admin_auth_test_utils import create_test_admin

db = SessionLocal()
admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="${tenantId}")
db.close()
print(json.dumps({"user_id": str(admin.id), "headers": headers}))
`);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
await context.addInitScript(({ token, tenantId, actorId }) => {
  window.localStorage.setItem("agrios_token", token);
  window.localStorage.setItem("agrios_tenant_id", tenantId);
  window.localStorage.setItem("agrios_user_id", actorId);
}, {
  token: admin.headers.Authorization.replace("Bearer ", ""),
  tenantId,
  actorId: admin.user_id,
});

const page = await context.newPage();

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

try {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });

  await page.getByText("Geography layer readiness").first().waitFor({ timeout: 30000 });
  await page.getByText("Cross-layer state and district matrix").waitFor({ timeout: 30000 });
  await page.getByText("LGD villages").first().waitFor({ timeout: 30000 });
  await page.getByText("Boundary outside matrix").first().waitFor({ timeout: 30000 });
  await page.getByText("State/district readiness matrix").first().waitFor({ timeout: 30000 });

  const okResponse = responses.find((response) => response.status === 200);
  if (!okResponse) {
    throw new Error(`Readiness API did not return 200: ${JSON.stringify(responses).slice(0, 1200)}`);
  }

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

  try {
    await page.screenshot({
      path: "smoke/screenshots/geography-layer-readiness.png",
      fullPage: false,
      timeout: 10000,
    });
  } catch (error) {
    console.warn(`Screenshot skipped: ${error.message}`);
  }

  console.log(JSON.stringify({
    schema_version: "geography_layer_readiness_web_smoke.v1",
    status: "PASSED",
    url,
    readiness_responses_seen: responses.length,
    screenshot: "web/smoke/screenshots/geography-layer-readiness.png",
  }, null, 2));
} finally {
  await browser.close();

  pythonJson(`
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent / "backend"))
from app.core.database import SessionLocal
from scripts.admin_auth_test_utils import delete_test_admin

db = SessionLocal()
delete_test_admin(db, "${admin.user_id}")
db.close()
print(json.dumps({"deleted": "${admin.user_id}"}))
`);
}
