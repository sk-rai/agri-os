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
  const readinessResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/v1/master-data/geography/layer-readiness") && response.status() === 200,
    { timeout: 60000 },
  );

  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });

  const okResponse = await readinessResponsePromise;
  const payload = await okResponse.json();

  if (payload.schema_version !== "geography_layer_readiness_matrix.v1") {
    throw new Error(`Unexpected readiness schema: ${payload.schema_version}`);
  }
  if (!payload.project_boundary_readiness) {
    throw new Error("Readiness payload missing project_boundary_readiness");
  }
  if (!payload.project_boundary_readiness.summary) {
    throw new Error("Readiness payload missing project_boundary_readiness.summary");
  }
  if (!payload.project_boundary_readiness.readiness) {
    throw new Error("Readiness payload missing project_boundary_readiness.readiness");
  }
  if (payload.project_boundary_readiness.readiness.ready_for_project_boundary_apply !== false) {
    throw new Error("Project boundary apply should remain disabled");
  }
  if (payload.project_boundary_readiness.readiness.ready_for_runtime_spatial_matching !== false) {
    throw new Error("Runtime spatial matching should remain disabled");
  }
  if (payload.project_boundary_readiness.readiness.ready_for_android_behavior_change !== false) {
    throw new Error("Android behavior should remain unchanged");
  }
  if ((payload.project_boundary_readiness.summary.raw_eligible_boundary_candidate_count || 0) <= 0) {
    throw new Error("Expected eligible boundary candidates to be visible");
  }
  if (!payload.selected_boundary_runtime_promotion_readiness) {
    throw new Error("Readiness payload missing selected_boundary_runtime_promotion_readiness");
  }
  if (payload.selected_boundary_runtime_promotion_readiness.readiness.ready_for_selected_runtime_promotion_apply !== false) {
    throw new Error("Selected boundary runtime promotion apply should remain disabled");
  }
  if (payload.selected_boundary_runtime_promotion_readiness.readiness.ready_for_runtime_lookup_enablement !== false) {
    throw new Error("Selected boundary runtime lookup should remain disabled");
  }
  if (payload.selected_boundary_runtime_promotion_readiness.readiness.ready_for_android_behavior_change !== false) {
    throw new Error("Selected boundary runtime should keep Android unchanged");
  }
  if (!payload.external_api_readiness) {
    throw new Error("Readiness payload missing external_api_readiness");
  }
  if (payload.external_api_readiness.readiness.ready_for_android_behavior_change !== false) {
    throw new Error("External API readiness should keep Android unchanged");
  }
  if (payload.external_api_readiness.guardrails.external_api_called !== false) {
    throw new Error("External API readiness should not call external APIs");
  }
  if (payload.external_api_readiness.guardrails.provider_worker_executed !== false) {
    throw new Error("External API readiness should not run provider workers");
  }
  if ((payload.external_api_readiness.summary.provider_surface_count || 0) <= 0) {
    throw new Error("Expected external API provider surfaces to be visible");
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
    project_boundary_summary: payload.project_boundary_readiness.summary,
    selected_boundary_runtime_summary: payload.selected_boundary_runtime_promotion_readiness.summary,
    external_api_summary: payload.external_api_readiness.summary,
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
