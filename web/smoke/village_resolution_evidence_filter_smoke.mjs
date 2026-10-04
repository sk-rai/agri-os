import { execFileSync } from "node:child_process";
import fs from "node:fs/promises";
import { chromium } from "playwright";

const webBaseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const tenantId = "default";
const screenshot = "smoke/screenshots/village-resolution-evidence-filter.png";

function pythonJson(code) {
  return JSON.parse(execFileSync("../venv/bin/python", ["-c", code], {
    cwd: process.cwd(), encoding: "utf-8",
  }));
}

const baseline = pythonJson([
  "import json,sys",
  "from pathlib import Path",
  "sys.path.insert(0,str(Path.cwd().parent/'backend'))",
  "from app.core.database import SessionLocal",
  "from sqlalchemy import text",
  "db=SessionLocal()",
  "counts=dict(db.execute(text(\"select (select count(*) from geography_village_resolution_evidence_reviews) reviews,(select count(*) from geography_village_resolution_evidence_review_events) events\")).mappings().one())",
  "db.close();print(json.dumps(counts))",
].join("\n"));
const admin = pythonJson([
  "import json,sys",
  "from pathlib import Path",
  "sys.path.insert(0,str(Path.cwd().parent/'backend'))",
  "from app.core.database import SessionLocal",
  "from scripts.admin_auth_test_utils import create_test_admin",
  "db=SessionLocal();user,headers=create_test_admin(db,role='ADMIN_VIEWER',tenant_id='default')",
  "user_id=str(user.id);db.close()",
  "print(json.dumps({'user_id':user_id,'headers':headers}))",
].join("\n"));

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1700, height: 1100 } });
  await context.addInitScript(({ token, actor }) => {
    localStorage.setItem("agrios_token", token);
    localStorage.setItem("agrios_tenant_id", "default");
    localStorage.setItem("agrios_user_id", actor);
  }, { token: admin.headers.Authorization.replace("Bearer ", ""), actor: admin.user_id });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => {
    if (message.type() === "error") errors.push(message.text());
  });
  const stateResponse = await context.request.get(
    "http://127.0.0.1:8000/api/v1/master-data/geography/states",
    { headers: admin.headers, timeout: 60000 },
  );
  if (!stateResponse.ok()) {
    throw new Error("State preflight failed: " + stateResponse.status() + " " + await stateResponse.text());
  }
  const states = await stateResponse.json();
  const rajasthan = states.find(row => row.canonical_name?.trim() === "Rajasthan");
  if (!rajasthan) throw new Error("Rajasthan was not returned by the canonical states API");
  await page.goto(webBaseUrl + "/geography-layer-readiness", {
    waitUntil: "domcontentloaded", timeout: 60000,
  });
  const filters = page.getByTestId("geography-readiness-filters");
  await filters.waitFor({ timeout: 60000 });
  const state = filters.getByLabel("State / UT", { exact: true });
  await page.waitForFunction(() =>
    Array.from(document.querySelectorAll('select[aria-label="State / UT"] option'))
      .some(option => Boolean(option.value)), null, { timeout: 60000 });
  await state.selectOption(rajasthan.id);
  const initial = page.waitForResponse(response =>
    response.url().includes("/geography/village-resolution?") && response.status() === 200,
    { timeout: 180000 });
  await filters.getByRole("button", { name: "View village resolution" }).click();
  await initial;
  const panel = page.getByTestId("village-resolution-panel");
  await panel.waitFor({ timeout: 60000 });

  await panel.getByLabel("Village review eligibility")
    .selectOption("TWO_SESSION_REVIEW_ELIGIBLE");
  const eligibleResponse = page.waitForResponse(response =>
    response.url().includes("review_eligibility=TWO_SESSION_REVIEW_ELIGIBLE") &&
    response.status() === 200, { timeout: 180000 });
  await panel.getByRole("button", { name: "Apply evidence filters" }).click();
  const eligible = await (await eligibleResponse).json();
  if (eligible.pagination.filtered_total !== 98) {
    throw new Error("Expected 98 Rajasthan two-session eligible villages");
  }
  if (eligible.items.some(item =>
    item.review_eligibility !== "TWO_SESSION_REVIEW_ELIGIBLE" ||
    item.source_collision !== false)) {
    throw new Error("Eligible filter returned an ineligible or colliding row");
  }

  await panel.getByLabel("Village review eligibility").selectOption("");
  await panel.getByLabel("Village source collision").selectOption("true");
  const collisionResponse = page.waitForResponse(response =>
    response.url().includes("source_collision=true") && response.status() === 200,
    { timeout: 180000 });
  await panel.getByRole("button", { name: "Apply evidence filters" }).click();
  const collisions = await (await collisionResponse).json();
  if (collisions.pagination.filtered_total !== 15 ||
      collisions.items.some(item => item.source_collision !== true)) {
    throw new Error("Expected exactly 15 Rajasthan collision rows");
  }
  await fs.mkdir("smoke/screenshots", { recursive: true });
  await panel.screenshot({ path: screenshot, timeout: 30000 });
  if (errors.length) throw new Error(errors.join(" | "));
  console.log(JSON.stringify({
    schema_version: "village_resolution_evidence_filter_web_smoke.v1",
    status: "PASSED",
    rajasthan_two_session_eligible: eligible.pagination.filtered_total,
    rajasthan_collision_rows: collisions.pagination.filtered_total,
    pagination_limit: eligible.pagination.limit,
    read_only: eligible.read_only && collisions.read_only,
    screenshot: "web/" + screenshot,
  }, null, 2));
} finally {
  await browser.close();
  const cleanup = pythonJson([
    "import json,sys",
    "from pathlib import Path",
    "sys.path.insert(0,str(Path.cwd().parent/'backend'))",
    "from app.core.database import SessionLocal",
    "from scripts.admin_auth_test_utils import delete_test_admin",
    "from sqlalchemy import text",
    "db=SessionLocal();delete_test_admin(db,'" + admin.user_id + "')",
    "counts=dict(db.execute(text(\"select (select count(*) from geography_village_resolution_evidence_reviews) reviews,(select count(*) from geography_village_resolution_evidence_review_events) events\")).mappings().one())",
    "db.close();print(json.dumps(counts))",
  ].join("\n"));
  if (cleanup.reviews !== baseline.reviews || cleanup.events !== baseline.events) {
    throw new Error("Read-only filter smoke changed review tables");
  }
}
