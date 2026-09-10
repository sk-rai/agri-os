import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const token = process.env.WEB_SWEEP_TOKEN;
const tenantId = process.env.WEB_SWEEP_TENANT_ID || "default";
const actorId = process.env.WEB_SWEEP_ACTOR_ID;
const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const reviewUrl =
  process.env.WEB_NWDP_BOUNDARY_REVIEW_URL ||
  `${baseUrl}/nwdp-boundary-review`;
const requestedProjectId = process.env.WEB_PROJECT_ID || "";

if (!token || !actorId) {
  console.error(
    "Missing WEB_SWEEP_TOKEN / WEB_SWEEP_ACTOR_ID. " +
    "Generate them with create_web_ui_smoke_session.py.",
  );
  process.exit(1);
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1600, height: 1100 },
});

const browserEvents = [];
const mutationResponses = [];

page.on("console", (message) => {
  browserEvents.push({
    type: "console",
    level: message.type(),
    text: message.text(),
  });
});

page.on("pageerror", (error) => {
  browserEvents.push({
    type: "pageerror",
    text: error.message,
  });
});

page.on("response", async (response) => {
  const url = response.url();
  const status = response.status();
  const isProjectMatching = url.includes(
    "/nwdp-boundary-project-matching/",
  );

  // Record every failed response and all project-matching responses.
  if (!isProjectMatching && status < 400) return;

  const body = await response.json().catch(async () =>
    (await response.text().catch(() => "")).slice(0, 1200),
  );
  const event = {
    type: "response",
    method: response.request().method(),
    status,
    url,
    body,
  };
  browserEvents.push(event);

  if (
    isProjectMatching &&
    ["PUT", "DELETE"].includes(event.method)
  ) {
    mutationResponses.push(event);
  }
});

page.on("requestfailed", (request) => {
  browserEvents.push({
    type: "requestfailed",
    method: request.method(),
    url: request.url(),
    error: request.failure()?.errorText || "unknown request failure",
  });
});

await page.addInitScript(({ token, tenantId, actorId }) => {
  window.localStorage.setItem("agrios_token", token);
  window.localStorage.setItem("agrios_tenant_id", tenantId);
  window.localStorage.setItem("agrios_user_id", actorId);
}, { token, tenantId, actorId });

async function captureFailure(name, error) {
  const screenshot = path.join(
    screenshotDir,
    `nwdp-project-boundary-assignment-${name}-failed.png`,
  );
  await page.screenshot({ path: screenshot, fullPage: true });
  const body = await page.locator("body").innerText().catch(() => "");

  throw new Error(
    `${error.message}\n` +
    `URL: ${page.url()}\n` +
    `Screenshot: ${screenshot}\n` +
    `Page excerpt: ${body.slice(0, 5000)}\n` +
    `Browser events: ${JSON.stringify(browserEvents.slice(-30), null, 2)}`,
  );
}

async function loadReviewPage() {
  await page.goto(reviewUrl, {
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });

  await page
    .getByRole("heading", { name: "NWDP Boundary Review" })
    .waitFor({ timeout: 30000 });

  await page
    .getByRole("heading", { name: "Project coverage preview" })
    .waitFor({ timeout: 30000 });

  await page
    .getByText("Assignments are project-scoped")
    .waitFor({ timeout: 15000 });

  // Projects and boundary summaries load asynchronously after page mount.
  // Wait for at least one real project option rather than relying on timing.
  await page.waitForFunction(() => {
    const labels = Array.from(document.querySelectorAll("label"));
    const projectLabel = labels.find((label) =>
      label.textContent?.trim().startsWith("Project"),
    );
    const select = projectLabel?.querySelector("select");
    return select
      ? Array.from(select.options).some((option) => option.value)
      : false;
  }, null, { timeout: 30000 });
}

async function selectProject(projectId) {
  const projectSelect = page.getByLabel("Project");
  await projectSelect.selectOption(projectId);
  await page
    .getByRole("button", { name: "Refresh project preview" })
    .click();
  await page.waitForTimeout(750);
}

async function findAssignableProject() {
  const projectSelect = page.getByLabel("Project");
  await projectSelect.waitFor({ timeout: 30000 });

  const options = await projectSelect.locator("option").evaluateAll((nodes) =>
    nodes
      .map((node) => ({
        value: node.value,
        label: node.textContent?.trim() || "",
      }))
      .filter((option) => option.value),
  );

  const candidates = requestedProjectId
    ? options.filter((option) => option.value === requestedProjectId)
    : options;

  if (requestedProjectId && candidates.length !== 1) {
    throw new Error(
      `Requested project ${requestedProjectId} is absent from the project selector`,
    );
  }

  for (const option of candidates) {
    await selectProject(option.value);

    const assignButtons = page.getByRole("button", {
      name: "Assign",
      exact: true,
    });

    if (await assignButtons.count()) {
      return option;
    }
  }

  throw new Error(
    "No project has an assignable VALIDATED direct-code boundary. " +
    "Create or select a project containing one of the validated Andaman villages.",
  );
}

function assertMutationGuardrails(event, expectedAction) {
  if (!event) {
    throw new Error(`No ${expectedAction} mutation response was captured`);
  }
  if (event.status !== 200) {
    throw new Error(
      `${event.method} returned ${event.status}: ${JSON.stringify(event.body)}`,
    );
  }
  if (event.body?.action !== expectedAction) {
    throw new Error(
      `Expected ${expectedAction}, received ${event.body?.action}`,
    );
  }

  const guardrails = event.body?.guardrails || {};
  const requiredFalse = [
    "android_behavior_changed",
    "candidate_activation_changed",
    "candidate_promotion_changed",
    "lgd_geography_overwritten",
    "lookup_api_enabled",
    "runtime_spatial_matching_changed",
    "runtime_tables_written",
    "source_runtime_eligibility_changed",
  ];

  for (const key of requiredFalse) {
    if (guardrails[key] !== false) {
      throw new Error(`Mutation guardrail ${key} was not false`);
    }
  }
}

try {
  await loadReviewPage();

  const selectedProject = await findAssignableProject();
  const projectId = selectedProject.value;

  const assignmentRow = page
    .locator("tbody tr")
    .filter({
      has: page.getByRole("button", { name: "Assign", exact: true }),
    })
    .first();

  const villageText = (
    await assignmentRow.locator("td").first().innerText()
  ).trim();

  const assignDialogs = [];
  page.on("dialog", async (dialog) => {
    assignDialogs.push(dialog.type());

    if (dialog.type() === "prompt") {
      await dialog.accept("Playwright project boundary assignment smoke");
      return;
    }
    await dialog.accept();
  });

  await assignmentRow
    .getByRole("button", { name: "Assign", exact: true })
    .click();

  await page
    .getByText("Boundary assignment: APPLIED")
    .waitFor({ timeout: 30000 });

  const applyResponse = mutationResponses.find(
    (event) => event.method === "PUT",
  );
  assertMutationGuardrails(applyResponse, "APPLIED");

  if (!assignDialogs.includes("prompt") || !assignDialogs.includes("confirm")) {
    throw new Error(
      `Assignment confirmation dialogs were not exercised: ${assignDialogs}`,
    );
  }

  await page.screenshot({
    path: path.join(
      screenshotDir,
      "nwdp-project-boundary-assignment-applied.png",
    ),
    fullPage: true,
  });

  // Reload the full page to prove that the assignment persisted in the API.
  await loadReviewPage();
  await selectProject(projectId);

  await page
    .getByText("Assigned", { exact: true })
    .first()
    .waitFor({ timeout: 30000 });

  await page.screenshot({
    path: path.join(
      screenshotDir,
      "nwdp-project-boundary-assignment-persisted.png",
    ),
    fullPage: true,
  });

  const unassignButton = page
    .getByRole("button", { name: "Unassign", exact: true })
    .first();

  await unassignButton.waitFor({ timeout: 15000 });
  await unassignButton.click();

  await page
    .getByText("Boundary assignment: ROLLED_BACK")
    .waitFor({ timeout: 30000 });

  const rollbackResponse = [...mutationResponses]
    .reverse()
    .find((event) => event.method === "DELETE");
  assertMutationGuardrails(rollbackResponse, "ROLLED_BACK");

  await selectProject(projectId);

  await page
    .getByRole("button", { name: "Assign", exact: true })
    .first()
    .waitFor({ timeout: 30000 });

  const activeAssignmentsResponse = [...browserEvents]
    .reverse()
    .find(
      (event) =>
        event.type === "response" &&
        event.method === "GET" &&
        event.url.includes(`/projects/${projectId}/assignments`) &&
        event.status === 200,
    );

  if (!activeAssignmentsResponse) {
    throw new Error("Final project assignment-list response was not captured");
  }

  if (activeAssignmentsResponse.body?.active_count !== 0) {
    throw new Error(
      `Expected zero active assignments after rollback, received ` +
      `${activeAssignmentsResponse.body?.active_count}`,
    );
  }

  // The UI requests active assignments only. Query inactive history
  // separately to prove that rollback retained its immutable audit row.
  const historyResponse = await page.request.get(
    `${apiBaseUrl}/api/v1/master-data/geography/` +
      `nwdp-boundary-project-matching/projects/${projectId}/` +
      "assignments?include_inactive=true",
    {
      headers: {
        Authorization: `Bearer ${token}`,
        "X-Tenant-ID": tenantId,
        "X-Actor-ID": actorId,
      },
    },
  );

  if (!historyResponse.ok()) {
    throw new Error(
      `Assignment history request returned ${historyResponse.status()}: ` +
      `${await historyResponse.text()}`,
    );
  }

  const assignmentHistory = await historyResponse.json();

  if (assignmentHistory.active_count !== 0) {
    throw new Error(
      `Expected zero active history rows, received ` +
      `${assignmentHistory.active_count}`,
    );
  }

  if ((assignmentHistory.count || 0) < 1) {
    throw new Error("Immutable rolled-back assignment history was not retained");
  }

  const rolledBackItem = assignmentHistory.items.find(
    (item) =>
      item.village_id === rollbackResponse.body.assignment.village_id &&
      item.match_status === "ROLLED_BACK" &&
      item.is_active === false,
  );

  if (!rolledBackItem) {
    throw new Error(
      "Rolled-back inactive assignment is missing from immutable history",
    );
  }

  await page.screenshot({
    path: path.join(
      screenshotDir,
      "nwdp-project-boundary-assignment-rolled-back.png",
    ),
    fullPage: true,
  });

  console.log(JSON.stringify({
    schema_version: "nwdp_project_boundary_assignment_web_smoke.v1",
    status: "PASSED",
    url: reviewUrl,
    tenant_id: tenantId,
    actor_id: actorId,
    project_id: projectId,
    project_label: selectedProject.label,
    village: villageText,
    apply_action: applyResponse.body.action,
    rollback_action: rollbackResponse.body.action,
    final_active_assignment_count:
      activeAssignmentsResponse.body.active_count,
    immutable_history_count:
      assignmentHistory.count,
    screenshots: [
      path.join(
        screenshotDir,
        "nwdp-project-boundary-assignment-applied.png",
      ),
      path.join(
        screenshotDir,
        "nwdp-project-boundary-assignment-persisted.png",
      ),
      path.join(
        screenshotDir,
        "nwdp-project-boundary-assignment-rolled-back.png",
      ),
    ],
    guardrails: {
      candidate_promotion_changed: false,
      runtime_eligibility_changed: false,
      runtime_lookup_enabled: false,
      android_behavior_changed: false,
    },
  }, null, 2));
} catch (error) {
  await captureFailure("exercise", error);
} finally {
  await browser.close();
}
