import { execFileSync } from "node:child_process";
import fs from "node:fs/promises";
import { chromium, request } from "playwright";

const webBaseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl = process.env.API_BASE_URL || "http://127.0.0.1:8000";
const pilotPath = "../data/staged/core_stack/promotion_review/20261004-village-resolution-evidence-review-pilot-v1/village_resolution_evidence_review_pilot.json";
const screenshotDir = "smoke/screenshots/village-evidence-review-pilot";

function pythonJson(code) {
  return JSON.parse(execFileSync("../venv/bin/python", ["-c", code], {
    cwd: process.cwd(), encoding: "utf-8",
  }));
}

const setup = pythonJson([
  "import json,sys",
  "from pathlib import Path",
  "sys.path.insert(0,str(Path.cwd().parent/'backend'))",
  "from app.core.database import SessionLocal",
  "from scripts.admin_auth_test_utils import create_test_admin",
  "from sqlalchemy import text",
  "db=SessionLocal()",
  "before=dict(db.execute(text(\"select (select count(*) from geography_villages where is_active) villages,(select count(*) from geography_village_pin_links where is_active) pins,(select count(*) from geography_boundary_runtime_crosswalks where is_active) runtime,(select count(*) from geography_village_resolution_evidence_reviews) reviews,(select count(*) from geography_village_resolution_evidence_review_events) events\")).mappings().one())",
  "p,ph=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id='default')",
  "a,ah=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id='default')",
  "pid,aid=str(p.id),str(a.id);db.close()",
  "print(json.dumps({'before':before,'primary':{'id':pid,'headers':ph},'second':{'id':aid,'headers':ah}}))",
].join("\n"));
const primaryToken = setup.primary.headers.Authorization.replace("Bearer ", "");
const primaryId = setup.primary.id;
const secondToken = setup.second.headers.Authorization.replace("Bearer ", "");
const secondId = setup.second.id;

const pilot = JSON.parse(await fs.readFile(pilotPath, "utf-8"));
const rows = pilot.rows || [];
if (pilot.schema_version !== "village_resolution_evidence_review_pilot.v1" ||
    rows.length !== 10 ||
    rows.some(row => row.best_match_rank !== 1 ||
      row.review_eligibility !== "TWO_SESSION_REVIEW_ELIGIBLE" ||
      row.source_collision !== false)) {
  throw new Error("Pilot manifest is not the pinned ten-row collision-free rank-one cohort");
}

function headers(token, actor) {
  return {
    Authorization: `Bearer ${token}`,
    "X-Tenant-ID": "default",
    "X-Actor-ID": actor,
  };
}

async function bodyOrThrow(response, label) {
  const text = await response.text();
  if (!response.ok()) throw new Error(`${label} failed (${response.status()}): ${text}`);
  return JSON.parse(text);
}

async function browserContext(browser, token, actor) {
  const context = await browser.newContext({ viewport: { width: 1700, height: 1100 } });
  await context.addInitScript(({ jwt, id }) => {
    localStorage.setItem("agrios_token", jwt);
    localStorage.setItem("agrios_tenant_id", "default");
    localStorage.setItem("agrios_user_id", id);
  }, { jwt: token, id: actor });
  return context;
}

async function openReviewPanel(page, authHeaders) {
  const statesResponse = await page.request.get(
    apiBaseUrl + "/api/v1/master-data/geography/states",
    { headers: authHeaders, timeout: 60000 },
  );
  const states = await bodyOrThrow(statesResponse, "State preflight");
  const rajasthan = states.find(row => row.canonical_name?.trim() === "Rajasthan");
  if (!rajasthan) throw new Error("Rajasthan state missing");
  await page.goto(webBaseUrl + "/geography-layer-readiness", {
    waitUntil: "domcontentloaded", timeout: 60000,
  });
  const filters = page.getByTestId("geography-readiness-filters");
  await filters.waitFor({ timeout: 60000 });
  await page.waitForFunction(() =>
    Array.from(document.querySelectorAll('select[aria-label="State / UT"] option'))
      .some(option => Boolean(option.value)), null, { timeout: 60000 });
  await filters.getByLabel("State / UT", { exact: true }).selectOption(rajasthan.id);
  const response = page.waitForResponse(candidate =>
    candidate.url().includes("/geography/village-resolution?") && candidate.status() === 200,
    { timeout: 180000 });
  await filters.getByRole("button", { name: "View village resolution" }).click();
  await response;
  const panel = page.getByTestId("village-evidence-review-panel");
  await panel.waitFor({ timeout: 60000 });
  return panel;
}

const primaryHeaders = headers(primaryToken, primaryId);
const secondHeaders = headers(secondToken, secondId);
const primaryApi = await request.newContext({ baseURL: apiBaseUrl, extraHTTPHeaders: primaryHeaders });
const secondApi = await request.newContext({ baseURL: apiBaseUrl, extraHTTPHeaders: secondHeaders });
const browser = await chromium.launch({ headless: true });
const reviewIds = [];
try {
  const before = await bodyOrThrow(
    await primaryApi.get("/api/v1/master-data/geography/village-resolution/reviews?limit=200"),
    "Initial review progress",
  );
  if (before.progress.application_authorized !== false) {
    throw new Error("Review progress crossed the no-apply boundary");
  }

  await fs.mkdir(screenshotDir, { recursive: true });
  const primaryContext = await browserContext(browser, primaryToken, primaryId);
  const primaryPage = await primaryContext.newPage();
  const beforePanel = await openReviewPanel(primaryPage, primaryHeaders);
  await beforePanel.screenshot({ path: screenshotDir + "/01-before.png" });

  for (const row of rows) {
    const result = await bodyOrThrow(
      await primaryApi.post("/api/v1/master-data/geography/village-resolution/reviews", {
        data: {
          evidence_item_id: row.evidence_item_id,
          decision: "ACCEPT_FOR_SECOND_REVIEW",
          notes: `Automated bounded pilot: rank-one exact-code evidence reviewed for LGD ${row.village_lgd_code}.`,
        },
      }),
      `Primary review for LGD ${row.village_lgd_code}`,
    );
    if (result.status !== "PENDING_SECOND_REVIEW" || result.second_review_required !== true) {
      throw new Error("Unexpected primary result for " + row.village_lgd_code);
    }
    reviewIds.push(result.review_id);
  }

  await primaryPage.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
  const primaryPanel = await openReviewPanel(primaryPage, primaryHeaders);
  await primaryPanel.getByText("Sign in as a different enterprise administrator").first().waitFor();
  await primaryPanel.screenshot({ path: screenshotDir + "/02-primary-complete.png" });

  for (let index = 0; index < reviewIds.length; index += 1) {
    const result = await bodyOrThrow(
      await secondApi.post(
        `/api/v1/master-data/geography/village-resolution/reviews/${reviewIds[index]}/second-review`,
        {
          data: {
            decision: "APPROVE",
            notes: `Independent automated pilot confirmation for sequence ${index + 1}; evidence only, no application.`,
            confirmation_phrase: "COMPLETE SECOND VILLAGE EVIDENCE REVIEW",
          },
        },
      ),
      `Second review for pilot sequence ${index + 1}`,
    );
    if (result.status !== "APPROVED" || result.application_authorized !== false) {
      throw new Error("Second review crossed the no-apply boundary");
    }
  }

  const secondContext = await browserContext(browser, secondToken, secondId);
  const secondPage = await secondContext.newPage();
  const finalPanel = await openReviewPanel(secondPage, secondHeaders);
  await finalPanel.getByText("PRIMARY ACCEPTED → SECOND APPROVED").first().waitFor();
  await finalPanel.screenshot({ path: screenshotDir + "/03-approved.png" });
  await secondPage.screenshot({ path: screenshotDir + "/04-approved-page.png", fullPage: true });

  const after = await bodyOrThrow(
    await secondApi.get("/api/v1/master-data/geography/village-resolution/reviews?status=APPROVED&limit=200"),
    "Final review progress",
  );
  const delta = {
    reviewed_total: after.progress.reviewed_total - before.progress.reviewed_total,
    approved: after.progress.approved - before.progress.approved,
    unreviewed: after.progress.unreviewed - before.progress.unreviewed,
  };
  if (delta.reviewed_total !== 10 || delta.approved !== 10 || delta.unreviewed !== -10) {
    throw new Error("Unexpected pilot progress delta: " + JSON.stringify(delta));
  }

  console.log(JSON.stringify({
    schema_version: "village_resolution_evidence_review_pilot_playwright.v1",
    status: "PASSED",
    persistent_audit_records: false,
    pilot_rows: 10,
    primary_admin_id: primaryId,
    second_admin_id: secondId,
    identities_are_distinct: true,
    progress_before: before.progress,
    progress_after: after.progress,
    progress_delta: delta,
    application_authorized: false,
    screenshots: [
      "web/" + screenshotDir + "/01-before.png",
      "web/" + screenshotDir + "/02-primary-complete.png",
      "web/" + screenshotDir + "/03-approved.png",
      "web/" + screenshotDir + "/04-approved-page.png",
    ],
  }, null, 2));
  await primaryContext.close();
  await secondContext.close();
} finally {
  await browser.close();
  await primaryApi.dispose();
  await secondApi.dispose();
  const cleanup = pythonJson([
    "import json,sys",
    "from pathlib import Path",
    "sys.path.insert(0,str(Path.cwd().parent/'backend'))",
    "from app.core.database import SessionLocal",
    "from scripts.admin_auth_test_utils import delete_test_admin",
    "from sqlalchemy import text",
    "db=SessionLocal()",
    "db.execute(text(\"delete from geography_village_resolution_evidence_reviews where primary_reviewer_id=cast(:p as uuid) or second_reviewer_id=cast(:a as uuid)\"),{'p':'" + primaryId + "','a':'" + secondId + "'})",
    "db.commit()",
    "delete_test_admin(db,'" + primaryId + "')",
    "delete_test_admin(db,'" + secondId + "')",
    "after=dict(db.execute(text(\"select (select count(*) from geography_villages where is_active) villages,(select count(*) from geography_village_pin_links where is_active) pins,(select count(*) from geography_boundary_runtime_crosswalks where is_active) runtime,(select count(*) from geography_village_resolution_evidence_reviews) reviews,(select count(*) from geography_village_resolution_evidence_review_events) events\")).mappings().one())",
    "db.close();print(json.dumps(after))",
  ].join("\n"));
  if (cleanup.villages !== setup.before.villages ||
      cleanup.pins !== setup.before.pins ||
      cleanup.runtime !== setup.before.runtime ||
      cleanup.reviews !== setup.before.reviews ||
      cleanup.events !== setup.before.events) {
    throw new Error("Pilot cleanup or protected geography check failed: " + JSON.stringify(cleanup));
  }
}

