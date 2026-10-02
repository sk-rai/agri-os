import { execFileSync } from "node:child_process";
import fs from "node:fs/promises";
import { chromium } from "playwright";

const webBaseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const tenantId = process.env.VILLAGE_RESOLUTION_TENANT_ID || "default";
const pageUrl = webBaseUrl + "/geography-layer-readiness";
const screenshot = "smoke/screenshots/village-resolution.png";

function pythonJson(code) {
  return JSON.parse(execFileSync("../venv/bin/python", ["-c", code], {
    cwd: process.cwd(), encoding: "utf-8",
  }));
}

const createCode = [
  "import json, sys",
  "from pathlib import Path",
  "sys.path.insert(0, str(Path.cwd().parent / 'backend'))",
  "from app.core.database import SessionLocal",
  "from scripts.admin_auth_test_utils import create_test_admin",
  "db=SessionLocal()",
  "admin,headers=create_test_admin(db,role='ADMIN_VIEWER',tenant_id='" + tenantId + "')",
  "db.close()",
  "print(json.dumps({'user_id':str(admin.id),'headers':headers}))",
].join("\n");
const admin = pythonJson(createCode);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
await context.addInitScript(({ token, tenant, actor }) => {
  localStorage.setItem("agrios_token", token);
  localStorage.setItem("agrios_tenant_id", tenant);
  localStorage.setItem("agrios_user_id", actor);
}, {
  token: admin.headers.Authorization.replace("Bearer ", ""),
  tenant: tenantId,
  actor: admin.user_id,
});
const page = await context.newPage();
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

function assertPayload(payload, expectedStatus = null) {
  if (payload.schema_version !== "lgd_pin_nwdp_village_resolution.v1") {
    throw new Error("Unexpected schema: " + payload.schema_version);
  }
  if (payload.read_only !== true) throw new Error("Endpoint must declare read_only=true");
  const summary = payload.summary;
  const partition = summary.fully_resolved + summary.pin_only + summary.nwdp_only + summary.unresolved;
  if (partition !== summary.total_villages) throw new Error("Resolution partition mismatch");
  if (payload.items.length > 50) throw new Error("UI page exceeded 50 rows");
  for (const item of payload.items) {
    if (!item.village_id || !item.village_lgd_code || !item.village_name) throw new Error("Village identity is incomplete");
    if (expectedStatus && item.resolution_status !== expectedStatus) throw new Error("Filtered status mismatch");
    if (item.has_effective_nwdp_mapping !== (item.has_candidate_mapping || item.has_active_runtime)) {
      throw new Error("Effective NWDP union is inconsistent");
    }
  }
}

try {
  await page.goto(pageUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  const filters = page.getByTestId("geography-readiness-filters");
  await filters.waitFor({ timeout: 60000 });
  const state = filters.getByLabel("State / UT", { exact: true });
  const district = filters.getByLabel("District", { exact: true });
  await page.waitForFunction(() => Array.from(document.querySelectorAll('select[aria-label="State / UT"] option')).some((row) => row.value), null, { timeout: 60000 });
  const stateValue = await state.locator("option").evaluateAll((rows) => rows.map((row) => row.value).find(Boolean));
  await state.selectOption(stateValue);
  await page.waitForFunction(() => Array.from(document.querySelectorAll('select[aria-label="District"] option')).some((row) => row.value), null, { timeout: 60000 });
  const districtValue = await district.locator("option").evaluateAll((rows) => rows.map((row) => row.value).find(Boolean));
  await district.selectOption(districtValue);

  const initialPromise = page.waitForResponse((response) => response.url().includes("/geography/village-resolution?") && response.status() === 200, { timeout: 180000 });
  await filters.getByRole("button", { name: "View village resolution" }).click();
  const initialPayload = await (await initialPromise).json();
  assertPayload(initialPayload);

  const panel = page.getByTestId("village-resolution-panel");
  await panel.waitFor({ timeout: 30000 });
  if (await panel.locator("tbody tr").count() !== initialPayload.items.length) throw new Error("Rendered row count mismatch");

  const filteredPromise = page.waitForResponse((response) => response.url().includes("resolution_status=FULLY_RESOLVED") && response.status() === 200, { timeout: 180000 });
  await panel.getByLabel("Village resolution status").selectOption("FULLY_RESOLVED");
  const filteredPayload = await (await filteredPromise).json();
  assertPayload(filteredPayload, "FULLY_RESOLVED");

  let paginationVerified = false;
  if (filteredPayload.pagination.has_more) {
    const nextPromise = page.waitForResponse((response) => response.url().includes("offset=50") && response.status() === 200, { timeout: 180000 });
    await panel.getByRole("button", { name: "Next" }).click();
    const nextPayload = await (await nextPromise).json();
    assertPayload(nextPayload, "FULLY_RESOLVED");
    if (nextPayload.pagination.offset !== 50) throw new Error("Next page offset is not 50");
    paginationVerified = true;
  }

  await fs.mkdir("smoke/screenshots", { recursive: true });
  await panel.screenshot({ path: screenshot, timeout: 30000 });
  if (browserErrors.length) throw new Error("Browser errors: " + browserErrors.join(" | "));
  console.log(JSON.stringify({
    schema_version: "village_resolution_web_smoke.v1",
    status: "PASSED",
    scope: { state_id: stateValue, district_id: districtValue },
    summary: initialPayload.summary,
    initial_rows: initialPayload.items.length,
    filtered_rows: filteredPayload.items.length,
    pagination_verified: paginationVerified,
    screenshot: "web/" + screenshot,
  }, null, 2));
} finally {
  await browser.close();
  const deleteCode = [
    "import json, sys",
    "from pathlib import Path",
    "sys.path.insert(0, str(Path.cwd().parent / 'backend'))",
    "from app.core.database import SessionLocal",
    "from scripts.admin_auth_test_utils import delete_test_admin",
    "db=SessionLocal()",
    "delete_test_admin(db,'" + admin.user_id + "')",
    "db.close()",
    "print(json.dumps({'deleted':'" + admin.user_id + "'}))",
  ].join("\n");
  pythonJson(deleteCode);
}
