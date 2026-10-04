import { execFileSync } from "node:child_process";
import fs from "node:fs/promises";
import { chromium } from "playwright";

const webBaseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl = process.env.API_BASE_URL || "http://127.0.0.1:8000";
const screenshot = "smoke/screenshots/village-resolution-evidence-review.png";

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
  "before=dict(db.execute(text(\"select (select count(*) from geography_villages where is_active) villages,(select count(*) from geography_village_pin_links where is_active) pins,(select count(*) from geography_boundary_runtime_crosswalks where is_active) runtime\")).mappings().one())",
  "p,ph=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id='default')",
  "a,ah=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id='default')",
  "pid,aid=str(p.id),str(a.id);db.close()",
  "print(json.dumps({'before':before,'proposer':{'id':pid,'headers':ph},'approver':{'id':aid,'headers':ah}}))",
].join("\n"));

function authContext(browser, identity) {
  return browser.newContext({ viewport: { width: 1700, height: 1100 } }).then(async context => {
    await context.addInitScript(({ token, actor }) => {
      localStorage.setItem("agrios_token", token);
      localStorage.setItem("agrios_tenant_id", "default");
      localStorage.setItem("agrios_user_id", actor);
    }, {
      token: identity.headers.Authorization.replace("Bearer ", ""),
      actor: identity.id,
    });
    return context;
  });
}

async function openEligibleQueue(page, headers) {
  const statesResponse = await page.request.get(
    apiBaseUrl + "/api/v1/master-data/geography/states",
    { headers, timeout: 60000 },
  );
  if (!statesResponse.ok()) throw new Error("State preflight failed");
  const states = await statesResponse.json();
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
  const initial = page.waitForResponse(response =>
    response.url().includes("/geography/village-resolution?") && response.status() === 200,
    { timeout: 180000 });
  await filters.getByRole("button", { name: "View village resolution" }).click();
  await initial;
  const panel = page.getByTestId("village-resolution-panel");
  await panel.waitFor({ timeout: 60000 });
  await panel.getByLabel("Village review eligibility")
    .selectOption("TWO_SESSION_REVIEW_ELIGIBLE");
  const eligible = page.waitForResponse(response =>
    response.url().includes("review_eligibility=TWO_SESSION_REVIEW_ELIGIBLE") &&
    response.status() === 200, { timeout: 180000 });
  await panel.getByRole("button", { name: "Apply evidence filters" }).click();
  await eligible;
  return panel;
}

const browser = await chromium.launch({ headless: true });
let reviewId = null;
try {
  const proposerContext = await authContext(browser, setup.proposer);
  const proposerPage = await proposerContext.newPage();
  const proposerPanel = await openEligibleQueue(proposerPage, setup.proposer.headers);
  const reviewButtons = proposerPanel.getByRole("button", { name: "Review evidence" });
  if (await reviewButtons.count() < 1) throw new Error("No eligible review control rendered");
  await reviewButtons.first().click();
  const reviewPanel = proposerPage.getByTestId("village-evidence-review-panel");
  await reviewPanel.getByLabel("Primary evidence decision")
    .selectOption("ACCEPT_FOR_SECOND_REVIEW");
  await reviewPanel.getByLabel("Primary review notes")
    .fill("Primary browser reviewer accepts the local evidence.");
  const primaryResponse = proposerPage.waitForResponse(response =>
    response.url().endsWith("/geography/village-resolution/reviews") &&
    response.request().method() === "POST", { timeout: 60000 });
  await reviewPanel.getByRole("button", { name: "Record primary decision" }).click();
  const primary = await primaryResponse;
  if (primary.status() !== 200) throw new Error("Primary review failed: " + await primary.text());
  reviewId = (await primary.json()).review_id;
  await reviewPanel.getByText("Sign in as a different enterprise administrator").waitFor();

  const selfReview = await proposerContext.request.post(
    apiBaseUrl + "/api/v1/master-data/geography/village-resolution/reviews/" +
      reviewId + "/second-review",
    {
      headers: setup.proposer.headers,
      data: {
        decision: "APPROVE",
        notes: "Self review must remain prohibited.",
        confirmation_phrase: "COMPLETE SECOND VILLAGE EVIDENCE REVIEW",
      },
    },
  );
  if (selfReview.status() !== 409) {
    throw new Error("Backend did not reject self review");
  }

  const approverContext = await authContext(browser, setup.approver);
  const approverPage = await approverContext.newPage();
  await openEligibleQueue(approverPage, setup.approver.headers);
  const approverPanel = approverPage.getByTestId("village-evidence-review-panel");
  await approverPanel.getByLabel("Second evidence decision").selectOption("APPROVE");
  await approverPanel.getByLabel("Second review notes")
    .fill("Independent browser reviewer confirms the local evidence.");
  await approverPanel.getByLabel("Second review confirmation")
    .fill("COMPLETE SECOND VILLAGE EVIDENCE REVIEW");
  const secondResponse = approverPage.waitForResponse(response =>
    response.url().includes("/second-review") &&
    response.request().method() === "POST", { timeout: 60000 });
  await approverPanel.getByRole("button", { name: "Complete independent review" }).click();
  const second = await secondResponse;
  if (second.status() !== 200) throw new Error("Second review failed: " + await second.text());
  const secondBody = await second.json();
  if (secondBody.status !== "APPROVED" || secondBody.application_authorized !== false) {
    throw new Error("Second review crossed the no-apply boundary");
  }
  await approverPanel.getByText("PRIMARY ACCEPTED → SECOND APPROVED").waitFor();
  await fs.mkdir("smoke/screenshots", { recursive: true });
  await approverPanel.screenshot({ path: screenshot, timeout: 30000 });
  console.log(JSON.stringify({
    schema_version: "village_resolution_evidence_review_web_smoke.v1",
    status: "PASSED",
    identities_are_distinct: setup.proposer.id !== setup.approver.id,
    self_review_http_status: selfReview.status(),
    primary_status: "PENDING_SECOND_REVIEW",
    second_status: secondBody.status,
    audit_actions: ["PRIMARY_ACCEPTED", "SECOND_APPROVED"],
    application_authorized: false,
    screenshot: "web/" + screenshot,
  }, null, 2));
  await proposerContext.close();
  await approverContext.close();
} finally {
  await browser.close();
  const cleanup = pythonJson([
    "import json,sys",
    "from pathlib import Path",
    "sys.path.insert(0,str(Path.cwd().parent/'backend'))",
    "from app.core.database import SessionLocal",
    "from scripts.admin_auth_test_utils import delete_test_admin",
    "from sqlalchemy import text",
    "db=SessionLocal()",
    "db.execute(text(\"delete from geography_village_resolution_evidence_reviews where primary_reviewer_id=cast(:p as uuid) or second_reviewer_id=cast(:a as uuid)\"),{'p':'" + setup.proposer.id + "','a':'" + setup.approver.id + "'})",
    "db.commit()",
    "delete_test_admin(db,'" + setup.proposer.id + "')",
    "delete_test_admin(db,'" + setup.approver.id + "')",
    "after=dict(db.execute(text(\"select (select count(*) from geography_villages where is_active) villages,(select count(*) from geography_village_pin_links where is_active) pins,(select count(*) from geography_boundary_runtime_crosswalks where is_active) runtime,(select count(*) from geography_village_resolution_evidence_reviews) reviews,(select count(*) from geography_village_resolution_evidence_review_events) events\")).mappings().one())",
    "db.close();print(json.dumps(after))",
  ].join("\n"));
  if (cleanup.villages !== setup.before.villages ||
      cleanup.pins !== setup.before.pins ||
      cleanup.runtime !== setup.before.runtime ||
      cleanup.reviews !== 0 || cleanup.events !== 0) {
    throw new Error("Smoke cleanup or protected geography check failed: " + JSON.stringify(cleanup));
  }
}
