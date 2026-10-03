import { execFileSync } from "node:child_process";
import fs from "node:fs/promises";
import { chromium } from "playwright";

const webBaseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl = process.env.API_BASE_URL || "http://127.0.0.1:8000";
const tenantId = "android-dynamic-test";
const projectId = "0f7e0a6b-8472-5d6d-8a14-a9d000000001";
const screenshot = "smoke/screenshots/project-village-resolution-review.png";

function pythonJson(code) {
  return JSON.parse(
    execFileSync("../venv/bin/python", ["-c", code], {
      cwd: process.cwd(),
      encoding: "utf-8",
    })
  );
}

function authHeaders(admin) {
  return {
    Authorization: admin.headers.Authorization,
    "X-Tenant-ID": tenantId,
    "X-Actor-ID": admin.user_id,
  };
}

async function authenticatedContext(browser, admin) {
  const context = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
  await context.addInitScript(
    ({ token, tenant, actor }) => {
      localStorage.setItem("agrios_token", token);
      localStorage.setItem("agrios_tenant_id", tenant);
      localStorage.setItem("agrios_user_id", actor);
      localStorage.setItem("agrios_role", "ENTERPRISE_ADMIN");
    },
    {
      token: admin.headers.Authorization.replace("Bearer ", ""),
      tenant: tenantId,
      actor: admin.user_id,
    }
  );
  await context.route("**/api/v1/projects*", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: projectId,
          name: "Android Dynamic Profile Test Project",
          tenant_id: tenantId,
          status: "ACTIVE",
          is_active: true,
        },
      ]),
    })
  );
  return context;
}

const createAdmins = [
  "import json,sys",
  "from pathlib import Path",
  "sys.path.insert(0,str(Path.cwd().parent/'backend'))",
  "from app.core.database import SessionLocal",
  "from scripts.admin_auth_test_utils import create_test_admin",
  "db=SessionLocal()",
  "proposer,proposer_headers=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id='" + tenantId + "')",
  "approver,approver_headers=create_test_admin(db,role='ENTERPRISE_ADMIN',tenant_id='" + tenantId + "')",
  "proposer_id=str(proposer.id)",
  "approver_id=str(approver.id)",
  "print(json.dumps({'proposer':{'user_id':proposer_id,'headers':proposer_headers},'approver':{'user_id':approver_id,'headers':approver_headers}}))",
  "db.close()",
].join("\n");

const protectedSnapshotCode = [
  "import json,sys",
  "from pathlib import Path",
  "sys.path.insert(0,str(Path.cwd().parent/'backend'))",
  "from sqlalchemy import text",
  "from app.core.database import SessionLocal",
  "db=SessionLocal()",
  "row=db.execute(text(\"select (select count(*) from geography_villages) villages,(select count(*) from geography_village_pin_links) pins,(select count(*) from geography_boundary_crosswalk_candidates) candidates,(select count(*) from geography_boundary_runtime_crosswalks) runtime,(select count(*) from geography_boundary_project_matches) project_matches\")).mappings().one()",
  "db.close()",
  "print(json.dumps(dict(row),sort_keys=True))",
].join("\n");

const admins = pythonJson(createAdmins);
const before = pythonJson(protectedSnapshotCode);
let resolutionId = null;
const browser = await chromium.launch({ headless: true });
const proposerContext = await authenticatedContext(browser, admins.proposer);
const approverContext = await authenticatedContext(browser, admins.approver);
const errors = [];

try {
  const proposerPage = await proposerContext.newPage();
  proposerPage.on("pageerror", (error) => errors.push("proposer: " + error.message));
  proposerPage.on("console", (message) => {
    if (message.type() === "error") errors.push("proposer: " + message.text());
  });

  await proposerPage.goto(webBaseUrl + "/geography-layer-readiness", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  const proposerPanel = proposerPage.getByTestId("project-village-resolution-panel");
  await proposerPanel.waitFor({ timeout: 60000 });
  await proposerPage.waitForFunction(
    (wanted) =>
      Array.from(
        document.querySelectorAll('select[aria-label="Resolution project"] option')
      ).some((row) => row.value === wanted),
    projectId,
    { timeout: 60000 }
  );
  await proposerPanel.getByLabel("Resolution project").selectOption(projectId);

  const worklistPromise = proposerPage.waitForResponse(
    (response) =>
      response.url().includes("/projects/" + projectId + "/worklist?") &&
      response.status() === 200,
    { timeout: 180000 }
  );
  await proposerPanel.getByRole("button", { name: "Load project worklist" }).click();
  const worklist = await (await worklistPromise).json();
  const selected = worklist.items.find(
    (item) => item.resolution_status === "FULLY_RESOLVED"
  );
  if (!selected) throw new Error("No FULLY_RESOLVED project village is available");

  await proposerPanel.getByLabel("Review " + selected.village_name).check();

  const candidatePromise = proposerPage.waitForResponse(
    (response) =>
      response.url().includes("/projects/" + projectId + "/nwdp-candidates?") &&
      response.status() === 200,
    { timeout: 60000 }
  );
  await proposerPanel.getByRole("button", { name: "Search NWDP" }).click();
  const candidates = await (await candidatePromise).json();
  const candidate = candidates.items.find(
    (item) => item.eligible_for_canonical_enrichment
  );
  if (!candidate) throw new Error("No eligible NWDP canonical-enrichment candidate");
  await proposerPanel
    .getByLabel("NWDP candidate", { exact: true })
    .selectOption(candidate.source_feature_id);

  const dryRunPromise = proposerPage.waitForResponse(
    (response) =>
      response.url().includes("/projects/" + projectId + "/dry-run") &&
      response.status() === 200,
    { timeout: 60000 }
  );
  await proposerPanel.getByRole("button", { name: "Validate dry run" }).click();
  const dryRun = await (await dryRunPromise).json();
  if (
    dryRun.status !== "VALID" ||
    dryRun.preview.would_write !== false ||
    dryRun.preview.would_be_android_visible !== false
  ) {
    throw new Error("Dry-run safety contract failed");
  }

  const proposalPromise = proposerPage.waitForResponse(
    (response) =>
      response.url().endsWith("/projects/" + projectId + "/proposals") &&
      response.request().method() === "POST",
    { timeout: 60000 }
  );
  await proposerPanel.getByRole("button", { name: "Create review proposal" }).click();
  const proposalResponse = await proposalPromise;
  const proposal = await proposalResponse.json();
  if (proposalResponse.status() !== 200 || proposal.status !== "DRAFT") {
    throw new Error("Proposal creation failed: " + JSON.stringify(proposal));
  }
  resolutionId = proposal.resolution_id;
  if (proposal.activation_enabled !== false || proposal.android_visible !== false) {
    throw new Error("Proposal unexpectedly enables activation or Android");
  }

  const selfApproval = await proposerContext.request.post(
    apiBaseUrl +
      "/api/v1/master-data/geography/project-village-resolutions/projects/" +
      projectId +
      "/resolutions/" +
      resolutionId +
      "/approve",
    {
      headers: authHeaders(admins.proposer),
      data: {
        confirmation_phrase: "APPROVE PROJECT CANONICAL ENRICHMENT",
        review_notes: "Self-approval must be rejected by the backend",
      },
    }
  );
  const selfApprovalPayload = await selfApproval.json();
  if (
    selfApproval.status() !== 409 ||
    selfApprovalPayload.detail !== "SECOND_ADMIN_MUST_DIFFER_FROM_PROPOSER"
  ) {
    throw new Error("Self-approval boundary failed: " + JSON.stringify(selfApprovalPayload));
  }

  const approverPreflight = await approverContext.request.get(
    apiBaseUrl +
      "/api/v1/master-data/geography/project-village-resolutions/projects/" +
      projectId +
      "/resolutions",
    { headers: authHeaders(admins.approver) }
  );
  if (approverPreflight.status() !== 200) {
    throw new Error(
      "Approver authentication preflight failed: " +
        approverPreflight.status() +
        " " +
        (await approverPreflight.text())
    );
  }
  const approverPage = await approverContext.newPage();
  approverPage.on("pageerror", (error) => errors.push("approver: " + error.message));
  approverPage.on("console", (message) => {
    if (message.type() === "error") errors.push("approver: " + message.text());
  });
  approverPage.on("response", (response) => {
    if (response.status() === 401 || response.status() === 403) {
      errors.push("approver auth response: " + response.status() + " " + response.url());
    }
  });
  await approverPage.goto(webBaseUrl + "/geography-layer-readiness", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  const approverPanel = approverPage.getByTestId("project-village-resolution-panel");
  try {
    await approverPanel.waitFor({ timeout: 60000 });
  } catch {
    await fs.mkdir("smoke/screenshots", { recursive: true });
    await approverPage.screenshot({
      path: "smoke/screenshots/project-village-resolution-review-approver-retry.png",
      fullPage: true,
    });
    const firstUrl = approverPage.url();
    const firstBody = (await approverPage.locator("body").innerText()).slice(0, 1000);
    await approverPage.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    try {
      await approverPanel.waitFor({ timeout: 180000 });
    } catch {
      throw new Error(
        "Approver panel did not render after retry: " +
          JSON.stringify({ firstUrl, firstBody, finalUrl: approverPage.url(), errors })
      );
    }
  }
  await approverPage.waitForFunction(
    (wanted) =>
      Array.from(
        document.querySelectorAll('select[aria-label="Resolution project"] option')
      ).some((row) => row.value === wanted),
    projectId,
    { timeout: 60000 }
  );
  await approverPanel.getByLabel("Resolution project").selectOption(projectId);

  const queuePromise = approverPage.waitForResponse(
    (response) =>
      response.url().endsWith("/projects/" + projectId + "/resolutions") &&
      response.status() === 200,
    { timeout: 60000 }
  );
  await approverPanel.getByRole("button", { name: "Load review queue" }).click();
  const queue = await (await queuePromise).json();
  if (queue.activation_enabled !== false) {
    throw new Error("Activation gate must remain disabled");
  }
  const draft = queue.items.find((item) => item.resolution_id === resolutionId);
  if (
    !draft ||
    draft.resolution_status !== "DRAFT" ||
    draft.events.map((event) => event.action).join(",") !== "PROPOSED"
  ) {
    throw new Error("Draft audit history is incorrect");
  }

  const approvalPromise = approverPage.waitForResponse(
    (response) =>
      response.url().endsWith("/resolutions/" + resolutionId + "/approve") &&
      response.request().method() === "POST",
    { timeout: 60000 }
  );
  await approverPanel.getByRole("button", { name: "Approve proposal" }).click();
  const approvalResponse = await approvalPromise;
  const approval = await approvalResponse.json();
  if (
    approvalResponse.status() !== 200 ||
    approval.status !== "APPROVED" ||
    approval.activation_enabled !== false
  ) {
    throw new Error("Independent approval failed: " + JSON.stringify(approval));
  }

  const finalQueueResponse = await approverContext.request.get(
    apiBaseUrl +
      "/api/v1/master-data/geography/project-village-resolutions/projects/" +
      projectId +
      "/resolutions",
    { headers: authHeaders(admins.approver) }
  );
  const finalQueue = await finalQueueResponse.json();
  const approved = finalQueue.items.find((item) => item.resolution_id === resolutionId);
  const actions = approved?.events.map((event) => event.action) || [];
  if (
    finalQueueResponse.status() !== 200 ||
    approved?.resolution_status !== "APPROVED" ||
    actions.join(",") !== "PROPOSED,APPROVED"
  ) {
    throw new Error("Approved audit history is incorrect: " + JSON.stringify(finalQueue));
  }

  if (
    (await approverPanel.getByRole("button", { name: "Activate approved resolution" }).count()) !== 0
  ) {
    throw new Error("Activation control must be hidden while the server gate is false");
  }

  if (JSON.stringify(pythonJson(protectedSnapshotCode)) !== JSON.stringify(before)) {
    throw new Error("Protected global geography state changed");
  }

  await fs.mkdir("smoke/screenshots", { recursive: true });
  await approverPanel.screenshot({ path: screenshot, timeout: 30000 });
  if (errors.length) throw new Error("Browser errors: " + errors.join(" | "));

  console.log(
    JSON.stringify(
      {
        schema_version: "project_village_resolution_two_session_web_smoke.v1",
        status: "PASSED",
        project_id: projectId,
        proposer_id: admins.proposer.user_id,
        approver_id: admins.approver.user_id,
        identities_are_distinct: admins.proposer.user_id !== admins.approver.user_id,
        proposal_status: "DRAFT",
        self_approval_http_status: selfApproval.status(),
        approval_status: approved.resolution_status,
        audit_actions: actions,
        activation_enabled: finalQueue.activation_enabled,
        activation_control_visible: false,
        android_visible: false,
        protected_global_geography_unchanged: true,
        screenshot: "web/" + screenshot,
      },
      null,
      2
    )
  );
} finally {
  await browser.close();
  const cleanup = [
    "import sys",
    "from pathlib import Path",
    "sys.path.insert(0,str(Path.cwd().parent/'backend'))",
    "from sqlalchemy import text",
    "from app.core.database import SessionLocal",
    "from scripts.admin_auth_test_utils import delete_test_admin",
    "db=SessionLocal()",
    "resolution_id='" + (resolutionId || "") + "'",
    "if resolution_id:",
    " db.execute(text('delete from geography_project_village_resolution_events where resolution_id=:id'),{'id':resolution_id})",
    " db.execute(text('delete from geography_project_village_resolutions where id=:id'),{'id':resolution_id})",
    " db.commit()",
    "delete_test_admin(db,'" + admins.proposer.user_id + "')",
    "delete_test_admin(db,'" + admins.approver.user_id + "')",
    "db.close()",
  ].join("\n");
  execFileSync("../venv/bin/python", ["-c", cleanup], {
    cwd: process.cwd(),
    stdio: "inherit",
  });
}
