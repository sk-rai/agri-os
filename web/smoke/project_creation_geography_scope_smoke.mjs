import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const token = process.env.WEB_SWEEP_TOKEN;
const actorId = process.env.WEB_SWEEP_ACTOR_ID;
const tenantId = process.env.WEB_SWEEP_TENANT_ID || "default";
const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const fixtureName =
  "Project Creation Geography Playwright Fixture";
const villageLgdCode = "645063";
const villageName = "Hoipoh*";
const creationReason =
  "Create project with canonical geography through Playwright";

if (!token || !actorId) {
  throw new Error(
    "Missing WEB_SWEEP_TOKEN or WEB_SWEEP_ACTOR_ID. " +
      "Generate them with create_web_ui_smoke_session.py.",
  );
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
const fixturePath =
  "/tmp/project-creation-geography-playwright-fixture.json";

await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1600, height: 1100 },
});

const browserEvents = [];
let activationPreflightRequestCount = 0;
let lifecycleHistoryRequestCount = 0;
let deactivationPreflightRequestCount = 0;
let completionPreflightRequestCount = 0;
let archivePreflightRequestCount = 0;
let restorePreflightRequestCount = 0;

page.on("request", (request) => {
  if (request.method() !== "GET") return;

  const url = new URL(request.url());

  if (
    url.pathname.includes(
      "/api/v1/master-data/geography/projects/",
    ) &&
    url.pathname.endsWith("/activation-preflight")
  ) {
    activationPreflightRequestCount += 1;
  }

  if (
    url.pathname.endsWith(
      `/api/v1/projects/${createdProject?.id}/lifecycle/audit`,
    )
  ) {
    lifecycleHistoryRequestCount += 1;
  }

  if (
    url.pathname.endsWith(
      `/api/v1/projects/${createdProject?.id}/deactivation-preflight`,
    )
  ) {
    deactivationPreflightRequestCount += 1;
  } else if (
    request.method() === "GET" &&
    url.pathname.endsWith("/completion-preflight")
  ) {
    completionPreflightRequestCount += 1;
  } else if (
    request.method() === "GET" &&
    url.pathname.endsWith("/archive-preflight")
  ) {
    archivePreflightRequestCount += 1;
  } else if (
    request.method() === "GET" &&
    url.pathname.endsWith("/restore-preflight")
  ) {
    restorePreflightRequestCount += 1;
  }
});

page.on("response", (response) => {
  if (response.status() >= 400) {
    browserEvents.push({
      type: "http_error",
      method: response.request().method(),
      status: response.status(),
      url: response.url(),
    });
  }
});

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

page.on("requestfailed", (request) => {
  browserEvents.push({
    type: "requestfailed",
    method: request.method(),
    url: request.url(),
    error: request.failure()?.errorText || "unknown",
  });
});

await page.addInitScript(
  ({ token, tenantId, actorId }) => {
    window.localStorage.setItem("agrios_token", token);
    window.localStorage.setItem("agrios_tenant_id", tenantId);
    window.localStorage.setItem("agrios_user_id", actorId);
  },
  { token, tenantId, actorId },
);

const headers = {
  Authorization: `Bearer ${token}`,
  "X-Tenant-ID": tenantId,
  "X-Actor-ID": actorId,
};

let createdProject = null;

try {
  const existingResponse = await page.request.get(
    `${apiBaseUrl}/api/v1/projects`,
    { headers },
  );

  if (!existingResponse.ok()) {
    throw new Error(
      `Project list returned ${existingResponse.status()}: ` +
        `${await existingResponse.text()}`,
    );
  }

  const existingProjects = await existingResponse.json();
  const existingMatches = existingProjects.filter(
    (project) => project.name === fixtureName,
  );

  if (existingMatches.length !== 0) {
    throw new Error(
      `Expected no existing project named "${fixtureName}", ` +
        `found ${existingMatches.length}`,
    );
  }

  await page.goto(`${baseUrl}/projects`, {
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });

  await page
    .getByRole("heading", { name: "Projects", exact: true })
    .waitFor({ timeout: 30000 });

  const newProjectButton = page.getByRole("button", {
    name: "+ New Project",
    exact: true,
  });

  await newProjectButton.waitFor({
    state: "visible",
    timeout: 30000,
  });

  await page.waitForFunction(
    () => {
      const buttons = Array.from(
        document.querySelectorAll("button"),
      );
      const button = buttons.find(
        (candidate) =>
          candidate.textContent?.trim() === "+ New Project",
      );
      return Boolean(button && !button.disabled);
    },
    undefined,
    { timeout: 30000 },
  );

  await newProjectButton.click();

  const createForm = page
    .getByRole("heading", { name: "Create Project", exact: true })
    .locator("..");

  await createForm
    .getByPlaceholder("Project Name")
    .fill(fixtureName);

  await createForm
    .getByPlaceholder("Crops (comma-separated: RICE,WHEAT)")
    .fill("RICE");

  const dateInputs = createForm.locator('input[type="date"]');
  await dateInputs.nth(0).fill("2026-01-01");
  await dateInputs.nth(1).fill("2026-12-31");

  const creationScope = createForm.getByLabel(
    "Project creation geography scope",
  );

  await creationScope
    .getByRole("button", {
      name: "Search across India",
      exact: true,
    })
    .click();

  const searchInput = creationScope.getByLabel(
    "Search villages",
    { exact: true },
  );

  const searchResponsePromise = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return (
        url.pathname.endsWith(
          "/api/v1/master-data/geography/villages/search",
        ) &&
        url.searchParams.get("q") === villageLgdCode &&
        !url.searchParams.has("district_id")
      );
    },
    { timeout: 30000 },
  );

  await searchInput.fill(villageLgdCode);

  const searchResponse = await searchResponsePromise;
  if (searchResponse.status() !== 200) {
    throw new Error(
      `Village search returned ${searchResponse.status()}`,
    );
  }

  const villageResult = creationScope
    .getByLabel("Village search results")
    .getByRole("option")
    .filter({ hasText: `LGD ${villageLgdCode}` })
    .first();

  await villageResult.waitFor({ timeout: 30000 });
  await villageResult.click();

  await creationScope
    .getByText(`LGD ${villageLgdCode}`, { exact: false })
    .last()
    .waitFor({ timeout: 30000 });

  await createForm
    .getByLabel("Initial geography scope reason", {
      exact: true,
    })
    .fill(creationReason);

  const createResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/v1/projects"),
    { timeout: 30000 },
  );

  await createForm
    .getByRole("button", {
      name: "Create Project",
      exact: true,
    })
    .click();

  const createResponse = await createResponsePromise;
  const createBody = await createResponse.json().catch(async () => ({
    raw: await createResponse.text(),
  }));

  if (createResponse.status() !== 201) {
    throw new Error(
      `Project creation returned ${createResponse.status()}: ` +
        `${JSON.stringify(createBody)}`,
    );
  }

  createdProject = createBody;

  const savedCodes =
    createdProject?.geography_scope?.village_lgd_codes || [];

  if (
    savedCodes.length !== 1 ||
    savedCodes[0] !== villageLgdCode
  ) {
    throw new Error(
      `Created project has unexpected geography scope: ` +
        `${JSON.stringify(savedCodes)}`,
    );
  }

  if (
    createdProject?.geography_scope?.source !==
    "admin_project_creation"
  ) {
    throw new Error(
      `Unexpected geography source: ` +
        `${createdProject?.geography_scope?.source}`,
    );
  }

  await fs.writeFile(
    fixturePath,
    JSON.stringify(
      {
        project_id: createdProject.id,
        project_name: fixtureName,
      },
      null,
      2,
    ),
    "utf8",
  );

  const projectCard = page
    .locator("div.bg-white.rounded-lg.shadow.p-4")
    .filter({
      has: page.getByRole("heading", {
        name: fixtureName,
        exact: true,
      }),
    })
    .first();

  await projectCard.waitFor({ timeout: 30000 });

  await projectCard
    .getByText("1 of 1 villages have an eligible boundary", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  if (activationPreflightRequestCount !== 0) {
    throw new Error(
      "Activation preflight loaded before the project-card action",
    );
  }

  const preflightResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().endsWith(
        `/api/v1/master-data/geography/projects/` +
          `${createdProject.id}/activation-preflight`,
      ),
    { timeout: 30000 },
  );

  await projectCard
    .getByRole("button", {
      name: "Activation preflight",
      exact: true,
    })
    .click();

  const preflightResponse = await preflightResponsePromise;
  const preflightBody = await preflightResponse.json().catch(
    async () => ({ raw: await preflightResponse.text() }),
  );

  if (preflightResponse.status() !== 200) {
    throw new Error(
      `Activation preflight returned ` +
        `${preflightResponse.status()}: ` +
        `${JSON.stringify(preflightBody)}`,
    );
  }

  if (
    preflightBody?.decision?.can_activate_geography !== true ||
    preflightBody?.decision?.blocker_count !== 0
  ) {
    throw new Error(
      `Created project did not pass activation preflight: ` +
        `${JSON.stringify(preflightBody)}`,
    );
  }

  const preflightPanel = projectCard.getByLabel(
    "Project geography activation preflight",
  );

  await preflightPanel
    .getByText("Ready for project activation", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  await preflightPanel
    .getByText("1/1", { exact: true })
    .waitFor({ timeout: 30000 });

  await preflightPanel
    .getByText("preflight is advisory", { exact: false })
    .waitFor({ timeout: 30000 });

  if (
    activationPreflightRequestCount < 1 ||
    activationPreflightRequestCount > 2
  ) {
    throw new Error(
      `Expected one lazy activation-preflight request ` +
        `(or two under React development Strict Mode), saw ` +
        `${activationPreflightRequestCount}`,
    );
  }

  const activationReason =
    "Activate project after successful geography preflight";

  await preflightPanel
    .getByLabel("Project activation reason", {
      exact: true,
    })
    .fill(activationReason);

  await preflightPanel
    .getByRole("button", {
      name: "Review project activation",
      exact: true,
    })
    .click();

  await preflightPanel
    .getByText("Confirm PLANNED → ACTIVE", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  const activationResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(
        `/api/v1/projects/${createdProject.id}/activate`,
      ),
    { timeout: 30000 },
  );

  await preflightPanel
    .getByRole("button", {
      name: "Confirm project activation",
      exact: true,
    })
    .click();

  const activationResponse = await activationResponsePromise;
  const activationBody = await activationResponse.json().catch(
    async () => ({ raw: await activationResponse.text() }),
  );

  if (activationResponse.status() !== 200) {
    throw new Error(
      `Project activation returned ` +
        `${activationResponse.status()}: ` +
        `${JSON.stringify(activationBody)}`,
    );
  }

  if (
    activationBody?.project?.status !== "ACTIVE" ||
    activationBody?.activation?.activated !== true ||
    activationBody?.activation?.idempotent !== false ||
    !activationBody?.activation?.audit_event_id ||
    activationBody?.activation?.preflight_fingerprint !==
      preflightBody?.decision?.preflight_fingerprint
  ) {
    throw new Error(
      `Unexpected activation response: ` +
        `${JSON.stringify(activationBody)}`,
    );
  }

  await projectCard
    .getByText("ACTIVE", { exact: true })
    .waitFor({ timeout: 30000 });

  if (
    lifecycleHistoryRequestCount !== 0 ||
    deactivationPreflightRequestCount !== 0
  ) {
    throw new Error(
      "Lifecycle and deactivation panels must load lazily: " +
        JSON.stringify({
          lifecycleHistoryRequestCount,
          deactivationPreflightRequestCount,
        }),
    );
  }

  const lifecycleResponsePromise = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return (
        response.request().method() === "GET" &&
        url.pathname.endsWith(
          `/api/v1/projects/${createdProject.id}/lifecycle/audit`,
        )
      );
    },
    { timeout: 30000 },
  );

  await projectCard
    .getByRole("button", {
      name: "Lifecycle history",
      exact: true,
    })
    .click();

  const lifecycleResponse = await lifecycleResponsePromise;
  const lifecycleBody = await lifecycleResponse.json().catch(
    async () => ({ raw: await lifecycleResponse.text() }),
  );

  if (
    lifecycleResponse.status() !== 200 ||
    lifecycleBody.schema_version !==
      "project_lifecycle_audit.v1" ||
    lifecycleBody.count !== 1 ||
    lifecycleBody.events?.[0]?.action !==
      "ACTIVATE_PROJECT" ||
    lifecycleBody.events?.[0]?.transition?.from_status !==
      "PLANNED" ||
    lifecycleBody.events?.[0]?.transition?.to_status !==
      "ACTIVE" ||
    lifecycleBody.events?.[0]?.reason !== activationReason ||
    lifecycleBody.events?.[0]?.preflight_fingerprint !==
      preflightBody.decision.preflight_fingerprint
  ) {
    throw new Error(
      `Unexpected lifecycle history: ` +
        `${JSON.stringify(lifecycleBody)}`,
    );
  }

  const lifecyclePanel = projectCard.getByLabel(
    "Project lifecycle history",
  );

  await lifecyclePanel
    .getByText("PLANNED → ACTIVE", { exact: true })
    .waitFor({ timeout: 30000 });

  await lifecyclePanel
    .getByText(activationReason, { exact: true })
    .waitFor({ timeout: 30000 });

  await lifecyclePanel
    .getByText(
      preflightBody.decision.preflight_fingerprint,
      { exact: false },
    )
    .waitFor({ timeout: 30000 });

  await lifecyclePanel
    .getByText("performs no database write", {
      exact: false,
    })
    .waitFor({ timeout: 30000 });

  if (
    lifecycleHistoryRequestCount < 1 ||
    lifecycleHistoryRequestCount > 2
  ) {
    throw new Error(
      `Expected one lifecycle-history request, or two under ` +
        `React development effect replay; saw ` +
        `${lifecycleHistoryRequestCount}`,
    );
  }

  const deactivationResponsePromise = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return (
        response.request().method() === "GET" &&
        url.pathname.endsWith(
          `/api/v1/projects/${createdProject.id}/deactivation-preflight`,
        )
      );
    },
    { timeout: 30000 },
  );

  await projectCard
    .getByRole("button", {
      name: "Deactivation preflight",
      exact: true,
    })
    .click();

  const deactivationResponse =
    await deactivationResponsePromise;
  const deactivationBody =
    await deactivationResponse.json().catch(
      async () => ({ raw: await deactivationResponse.text() }),
    );

  if (
    deactivationResponse.status() !== 200 ||
    deactivationBody.schema_version !==
      "project_deactivation_preflight.v2" ||
    deactivationBody.mode !== "READ_ONLY_PREFLIGHT" ||
    deactivationBody.project?.status !== "ACTIVE" ||
    deactivationBody.decision?.can_deactivate !== true ||
    deactivationBody.decision?.deactivation_supported !==
      true ||
    deactivationBody.decision?.blocker_count !== 0 ||
    typeof deactivationBody.decision
      ?.preflight_fingerprint !== "string" ||
    deactivationBody.decision
      .preflight_fingerprint.length !== 64 ||
    Object.values(
      deactivationBody.operational_counts || {},
    ).some((count) => count !== 0)
  ) {
    throw new Error(
      `Unexpected deactivation preflight: ` +
        `${JSON.stringify(deactivationBody)}`,
    );
  }

  const deactivationPanel = projectCard.getByLabel(
    "Project deactivation preflight",
  );

  await deactivationPanel
    .getByText("No operational blockers detected", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  await deactivationPanel
    .getByText("does not change project status", {
      exact: false,
    })
    .waitFor({ timeout: 30000 });

  if (
    deactivationPreflightRequestCount < 1 ||
    deactivationPreflightRequestCount > 2
  ) {
    throw new Error(
      `Expected one deactivation-preflight request, or two under ` +
        `React development effect replay; saw ` +
        `${deactivationPreflightRequestCount}`,
    );
  }

  const deactivationReason =
    "Return project to planning after browser operational review";

  await deactivationPanel
    .getByLabel("Project deactivation reason", {
      exact: true,
    })
    .fill(deactivationReason);

  await deactivationPanel
    .getByRole("button", {
      name: "Review project deactivation",
      exact: true,
    })
    .click();

  await deactivationPanel
    .getByText("Confirm ACTIVE → PLANNED", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  const deactivateResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(
        `/api/v1/projects/${createdProject.id}/deactivate`,
      ),
    { timeout: 30000 },
  );

  await deactivationPanel
    .getByRole("button", {
      name: "Confirm project deactivation",
      exact: true,
    })
    .click();

  const deactivateResponse = await deactivateResponsePromise;
  const deactivateBody = await deactivateResponse.json().catch(
    async () => ({ raw: await deactivateResponse.text() }),
  );

  if (
    deactivateResponse.status() !== 200 ||
    deactivateBody?.project?.status !== "PLANNED" ||
    deactivateBody?.deactivation?.deactivated !== true ||
    deactivateBody?.deactivation?.idempotent !== false ||
    !deactivateBody?.deactivation?.audit_event_id ||
    deactivateBody?.deactivation?.preflight_fingerprint !==
      deactivationBody.decision.preflight_fingerprint
  ) {
    throw new Error(
      `Unexpected project deactivation response: ` +
        `${JSON.stringify(deactivateBody)}`,
    );
  }

  const deactivationGuardrails =
    deactivateBody.guardrails || {};

  if (
    deactivationGuardrails.boundary_assignments_changed !==
      false ||
    deactivationGuardrails.boundary_candidates_activated !==
      false ||
    deactivationGuardrails.boundary_candidates_promoted !==
      false ||
    deactivationGuardrails.runtime_tables_written !== false ||
    deactivationGuardrails.runtime_lookup_enabled !== false ||
    deactivationGuardrails.android_behavior_changed !== false
  ) {
    throw new Error(
      `Deactivation guardrails changed unexpectedly: ` +
        `${JSON.stringify(deactivationGuardrails)}`,
    );
  }

  await projectCard
    .getByText("PLANNED", { exact: true })
    .waitFor({ timeout: 30000 });

  await projectCard
    .getByRole("button", {
      name: "Activation preflight",
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  if (
    await projectCard
      .getByRole("button", {
        name: "Deactivation preflight",
        exact: true,
      })
      .count()
  ) {
    throw new Error(
      "Deactivation action remained visible after PLANNED status persisted",
    );
  }

  const hideLifecycleButton = projectCard.getByRole(
    "button",
    {
      name: "Hide lifecycle history",
      exact: true,
    },
  );

  if (await hideLifecycleButton.count()) {
    await hideLifecycleButton.click();
  }

  const updatedLifecycleResponsePromise =
    page.waitForResponse(
      (response) => {
        const url = new URL(response.url());
        return (
          response.request().method() === "GET" &&
          url.pathname.endsWith(
            `/api/v1/projects/${createdProject.id}/lifecycle/audit`,
          )
        );
      },
      { timeout: 30000 },
    );

  await projectCard
    .getByRole("button", {
      name: "Lifecycle history",
      exact: true,
    })
    .click();

  const updatedLifecycleResponse =
    await updatedLifecycleResponsePromise;
  const updatedLifecycleBody =
    await updatedLifecycleResponse.json().catch(
      async () => ({
        raw: await updatedLifecycleResponse.text(),
      }),
    );

  if (
    updatedLifecycleResponse.status() !== 200 ||
    updatedLifecycleBody.count !== 2 ||
    updatedLifecycleBody.events?.[0]?.action !==
      "DEACTIVATE_PROJECT" ||
    updatedLifecycleBody.events?.[0]?.transition
      ?.from_status !== "ACTIVE" ||
    updatedLifecycleBody.events?.[0]?.transition
      ?.to_status !== "PLANNED" ||
    updatedLifecycleBody.events?.[0]?.reason !==
      deactivationReason ||
    updatedLifecycleBody.events?.[0]
      ?.preflight_fingerprint !==
        deactivationBody.decision.preflight_fingerprint ||
    updatedLifecycleBody.events?.[1]?.action !==
      "ACTIVATE_PROJECT"
  ) {
    throw new Error(
      `Unexpected lifecycle history after deactivation: ` +
        `${JSON.stringify(updatedLifecycleBody)}`,
    );
  }

  const updatedLifecyclePanel = projectCard.getByLabel(
    "Project lifecycle history",
  );

  await updatedLifecyclePanel
    .getByText("ACTIVE → PLANNED", { exact: true })
    .waitFor({ timeout: 30000 });

  await updatedLifecyclePanel
    .getByText(deactivationReason, { exact: true })
    .waitFor({ timeout: 30000 });

  await updatedLifecyclePanel
    .getByText(
      deactivationBody.decision.preflight_fingerprint,
      { exact: false },
    )
    .waitFor({ timeout: 30000 });

  const reactivationPreflightResponse =
    await page.request.get(
      `${apiBaseUrl}/api/v1/master-data/geography/projects/` +
        `${createdProject.id}/activation-preflight`,
      { headers },
    );

  if (!reactivationPreflightResponse.ok()) {
    throw new Error(
      `Reactivation preflight returned ` +
        `${reactivationPreflightResponse.status()}: ` +
        `${await reactivationPreflightResponse.text()}`,
    );
  }

  const reactivationPreflight =
    await reactivationPreflightResponse.json();
  const reactivationReason =
    "Reactivate project for completion browser verification";

  const reactivationResponse = await page.request.post(
    `${apiBaseUrl}/api/v1/projects/${createdProject.id}/activate`,
    {
      headers,
      data: {
        reason: reactivationReason,
        preflight_fingerprint:
          reactivationPreflight.decision.preflight_fingerprint,
      },
    },
  );

  if (!reactivationResponse.ok()) {
    throw new Error(
      `Project reactivation returned ` +
        `${reactivationResponse.status()}: ` +
        `${await reactivationResponse.text()}`,
    );
  }

  const reactivationBody = await reactivationResponse.json();
  if (
    reactivationBody.project?.status !== "ACTIVE" ||
    reactivationBody.activation?.activated !== true
  ) {
    throw new Error(
      `Unexpected reactivation response: ` +
        `${JSON.stringify(reactivationBody)}`,
    );
  }

  await page.reload({
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });

  const completedProjectCard = page
    .locator("div.bg-white.rounded-lg.shadow.p-4")
    .filter({
      has: page.getByRole("heading", {
        name: fixtureName,
        exact: true,
      }),
    })
    .first();

  await completedProjectCard
    .getByText("ACTIVE", { exact: true })
    .waitFor({ timeout: 30000 });

  const completionPreflightResponsePromise =
    page.waitForResponse(
      (response) => {
        const url = new URL(response.url());
        return (
          response.request().method() === "GET" &&
          url.pathname.endsWith(
            `/api/v1/projects/${createdProject.id}/completion-preflight`,
          )
        );
      },
      { timeout: 30000 },
    );

  await completedProjectCard
    .getByRole("button", {
      name: "Completion preflight",
      exact: true,
    })
    .click();

  const completionPreflightResponse =
    await completionPreflightResponsePromise;
  const completionPreflightBody =
    await completionPreflightResponse.json().catch(
      async () => ({
        raw: await completionPreflightResponse.text(),
      }),
    );

  if (
    completionPreflightResponse.status() !== 200 ||
    completionPreflightBody.schema_version !==
      "project_completion_preflight.v1" ||
    completionPreflightBody.mode !== "READ_ONLY_PREFLIGHT" ||
    completionPreflightBody.project?.status !== "ACTIVE" ||
    completionPreflightBody.decision?.can_complete !== true ||
    completionPreflightBody.decision?.completion_supported !==
      true ||
    completionPreflightBody.decision?.blocker_count !== 0 ||
    typeof completionPreflightBody.decision
      ?.preflight_fingerprint !== "string" ||
    completionPreflightBody.decision
      .preflight_fingerprint.length !== 64 ||
    Object.values(
      completionPreflightBody.operational_counts || {},
    ).some((count) => count !== 0)
  ) {
    throw new Error(
      `Unexpected completion preflight: ` +
        `${JSON.stringify(completionPreflightBody)}`,
    );
  }

  const completionPanel = completedProjectCard.getByLabel(
    "Project completion preflight",
  );

  await completionPanel
    .getByText("No operational blockers detected", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  await completionPanel
    .getByText("does not change project status", {
      exact: false,
    })
    .waitFor({ timeout: 30000 });

  if (
    completionPreflightRequestCount < 1 ||
    completionPreflightRequestCount > 2
  ) {
    throw new Error(
      `Expected one completion-preflight request, or two under ` +
        `React development effect replay; saw ` +
        `${completionPreflightRequestCount}`,
    );
  }

  const completionReason =
    "Complete project after browser terminal-work review";

  await completionPanel
    .getByLabel("Project completion reason", {
      exact: true,
    })
    .fill(completionReason);

  await completionPanel
    .getByRole("button", {
      name: "Review project completion",
      exact: true,
    })
    .click();

  await completionPanel
    .getByText("Confirm ACTIVE → COMPLETED", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  const completeResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(
        `/api/v1/projects/${createdProject.id}/complete`,
      ),
    { timeout: 30000 },
  );

  await completionPanel
    .getByRole("button", {
      name: "Confirm project completion",
      exact: true,
    })
    .click();

  const completeResponse = await completeResponsePromise;
  const completeBody = await completeResponse.json().catch(
    async () => ({ raw: await completeResponse.text() }),
  );

  if (
    completeResponse.status() !== 200 ||
    completeBody.project?.status !== "COMPLETED" ||
    completeBody.completion?.completed !== true ||
    completeBody.completion?.idempotent !== false ||
    !completeBody.completion?.audit_event_id ||
    completeBody.completion?.preflight_fingerprint !==
      completionPreflightBody.decision.preflight_fingerprint
  ) {
    throw new Error(
      `Unexpected project completion response: ` +
        `${JSON.stringify(completeBody)}`,
    );
  }

  const completionGuardrails = completeBody.guardrails || {};
  if (
    completionGuardrails.operational_records_changed !== false ||
    completionGuardrails.boundary_assignments_changed !== false ||
    completionGuardrails.boundary_candidates_activated !== false ||
    completionGuardrails.boundary_candidates_promoted !== false ||
    completionGuardrails.runtime_tables_written !== false ||
    completionGuardrails.runtime_lookup_enabled !== false ||
    completionGuardrails.android_behavior_changed !== false
  ) {
    throw new Error(
      `Completion guardrails changed unexpectedly: ` +
        `${JSON.stringify(completionGuardrails)}`,
    );
  }

  await completedProjectCard
    .getByText("COMPLETED", { exact: true })
    .waitFor({ timeout: 30000 });

  if (
    await completedProjectCard
      .getByRole("button", {
        name: "Completion preflight",
        exact: true,
      })
      .count()
  ) {
    throw new Error(
      "Completion action remained visible after COMPLETED status persisted",
    );
  }


  const archivePreflightResponsePromise =
    page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        response.url().endsWith(
          `/api/v1/projects/${createdProject.id}/archive-preflight`,
        ),
      { timeout: 30000 },
    );

  await completedProjectCard
    .getByRole("button", {
      name: "Archive preflight",
      exact: true,
    })
    .click();

  const archivePreflightResponse =
    await archivePreflightResponsePromise;
  const archivePreflightBody =
    await archivePreflightResponse.json().catch(
      async () => ({
        raw: await archivePreflightResponse.text(),
      }),
    );

  if (
    archivePreflightResponse.status() !== 200 ||
    archivePreflightBody.schema_version !==
      "project_archive_preflight.v1" ||
    archivePreflightBody.mode !== "READ_ONLY_PREFLIGHT" ||
    archivePreflightBody.project?.status !== "COMPLETED" ||
    archivePreflightBody.decision?.can_archive !== true ||
    archivePreflightBody.decision?.archive_supported !== true ||
    archivePreflightBody.decision?.blocker_count !== 0 ||
    typeof archivePreflightBody.decision
      ?.preflight_fingerprint !== "string" ||
    archivePreflightBody.decision
      .preflight_fingerprint.length !== 64 ||
    Object.values(
      archivePreflightBody.operational_counts || {},
    ).some((count) => count !== 0)
  ) {
    throw new Error(
      `Unexpected archive preflight: ` +
        `${JSON.stringify(archivePreflightBody)}`,
    );
  }

  const archivePanel = completedProjectCard.getByLabel(
    "Project archive preflight",
  );

  await archivePanel
    .getByText("No operational blockers detected", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  if (
    archivePreflightRequestCount < 1 ||
    archivePreflightRequestCount > 2
  ) {
    throw new Error(
      `Expected one archive-preflight request, or two under ` +
        `React development effect replay; saw ` +
        `${archivePreflightRequestCount}`,
    );
  }

  const archiveReason =
    "Archive completed project after browser retention review";

  await archivePanel
    .getByLabel("Project archive reason", {
      exact: true,
    })
    .fill(archiveReason);

  await archivePanel
    .getByRole("button", {
      name: "Review project archive",
      exact: true,
    })
    .click();

  await archivePanel
    .getByText("Confirm COMPLETED → ARCHIVED", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  const archiveResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(
        `/api/v1/projects/${createdProject.id}/archive`,
      ),
    { timeout: 30000 },
  );

  await archivePanel
    .getByRole("button", {
      name: "Confirm project archive",
      exact: true,
    })
    .click();

  const archiveResponse = await archiveResponsePromise;
  const archiveBody = await archiveResponse.json().catch(
    async () => ({ raw: await archiveResponse.text() }),
  );

  if (
    archiveResponse.status() !== 200 ||
    archiveBody.project?.status !== "ARCHIVED" ||
    archiveBody.archive?.archived !== true ||
    archiveBody.archive?.idempotent !== false ||
    !archiveBody.archive?.audit_event_id ||
    archiveBody.archive?.preflight_fingerprint !==
      archivePreflightBody.decision.preflight_fingerprint ||
    Object.values(archiveBody.guardrails || {}).some(
      (value) => value !== false,
    )
  ) {
    throw new Error(
      `Unexpected project archive response: ` +
        `${JSON.stringify(archiveBody)}`,
    );
  }

  await completedProjectCard
    .getByText("ARCHIVED", { exact: true })
    .waitFor({ timeout: 30000 });

  if (
    await completedProjectCard
      .getByRole("button", {
        name: "Archive preflight",
        exact: true,
      })
      .count()
  ) {
    throw new Error(
      "Archive action remained visible after ARCHIVED status persisted",
    );
  }

  const restorePreflightResponsePromise =
    page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        response.url().endsWith(
          `/api/v1/projects/${createdProject.id}/restore-preflight`,
        ),
      { timeout: 30000 },
    );

  await completedProjectCard
    .getByRole("button", {
      name: "Restore preflight",
      exact: true,
    })
    .click();

  const restorePreflightResponse =
    await restorePreflightResponsePromise;
  const restorePreflightBody =
    await restorePreflightResponse.json().catch(
      async () => ({
        raw: await restorePreflightResponse.text(),
      }),
    );

  if (
    restorePreflightResponse.status() !== 200 ||
    restorePreflightBody.schema_version !==
      "project_restore_preflight.v1" ||
    restorePreflightBody.mode !== "READ_ONLY_PREFLIGHT" ||
    restorePreflightBody.project?.status !== "ARCHIVED" ||
    restorePreflightBody.decision?.can_restore !== true ||
    restorePreflightBody.decision?.restore_supported !== true ||
    restorePreflightBody.decision?.blocker_count !== 0 ||
    typeof restorePreflightBody.decision
      ?.preflight_fingerprint !== "string" ||
    restorePreflightBody.decision
      .preflight_fingerprint.length !== 64 ||
    !restorePreflightBody.prior_archive_event?.id
  ) {
    throw new Error(
      `Unexpected restore preflight: ` +
        `${JSON.stringify(restorePreflightBody)}`,
    );
  }

  const restorePanel = completedProjectCard.getByLabel(
    "Project restore preflight",
  );

  await restorePanel
    .getByText("Immutable archive evidence", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  if (
    restorePreflightRequestCount < 1 ||
    restorePreflightRequestCount > 2
  ) {
    throw new Error(
      `Expected one restore-preflight request, or two under ` +
        `React development effect replay; saw ` +
        `${restorePreflightRequestCount}`,
    );
  }

  const restoreReason =
    "Restore archived project after browser governance review";

  await restorePanel
    .getByLabel("Project restore reason", {
      exact: true,
    })
    .fill(restoreReason);

  await restorePanel
    .getByRole("button", {
      name: "Review project restore",
      exact: true,
    })
    .click();

  await restorePanel
    .getByText("Confirm ARCHIVED → COMPLETED", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  const restoreResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(
        `/api/v1/projects/${createdProject.id}/restore`,
      ),
    { timeout: 30000 },
  );

  await restorePanel
    .getByRole("button", {
      name: "Confirm project restore",
      exact: true,
    })
    .click();

  const restoreResponse = await restoreResponsePromise;
  const restoreBody = await restoreResponse.json().catch(
    async () => ({ raw: await restoreResponse.text() }),
  );

  if (
    restoreResponse.status() !== 200 ||
    restoreBody.project?.status !== "COMPLETED" ||
    restoreBody.restore?.restored !== true ||
    restoreBody.restore?.idempotent !== false ||
    !restoreBody.restore?.audit_event_id ||
    restoreBody.restore?.archive_audit_event_id !==
      archiveBody.archive.audit_event_id ||
    restoreBody.restore?.preflight_fingerprint !==
      restorePreflightBody.decision.preflight_fingerprint ||
    Object.values(restoreBody.guardrails || {}).some(
      (value) => value !== false,
    )
  ) {
    throw new Error(
      `Unexpected project restore response: ` +
        `${JSON.stringify(restoreBody)}`,
    );
  }

  await completedProjectCard
    .getByText("COMPLETED", { exact: true })
    .waitFor({ timeout: 30000 });

  if (
    await completedProjectCard
      .getByRole("button", {
        name: "Restore preflight",
        exact: true,
      })
      .count()
  ) {
    throw new Error(
      "Restore action remained visible after COMPLETED status persisted",
    );
  }

  const completionHistoryResponse = await page.request.get(
    `${apiBaseUrl}/api/v1/projects/` +
      `${createdProject.id}/lifecycle/audit`,
    { headers },
  );
  const completionHistory =
    await completionHistoryResponse.json();

  if (
    completionHistoryResponse.status() !== 200 ||
    completionHistory.count !== 6 ||
    completionHistory.events?.[0]?.action !==
      "RESTORE_PROJECT" ||
    completionHistory.events?.[0]?.transition
      ?.from_status !== "ARCHIVED" ||
    completionHistory.events?.[0]?.transition
      ?.to_status !== "COMPLETED" ||
    completionHistory.events?.[0]?.reason !== restoreReason ||
    completionHistory.events?.[1]?.action !==
      "ARCHIVE_PROJECT" ||
    completionHistory.events?.[1]?.transition
      ?.from_status !== "COMPLETED" ||
    completionHistory.events?.[1]?.transition
      ?.to_status !== "ARCHIVED" ||
    completionHistory.events?.[1]?.reason !== archiveReason ||
    completionHistory.events?.[2]?.action !==
      "COMPLETE_PROJECT" ||
    completionHistory.events?.[2]?.reason !==
      completionReason
  ) {
    throw new Error(
      `Unexpected lifecycle history after completion: ` +
        `${JSON.stringify(completionHistory)}`,
    );
  }

  const lifecycleAuditResponse = await page.request.get(
    `${apiBaseUrl}/api/v1/app-config/projects/` +
      `${createdProject.id}/config/audit`,
    { headers },
  );

  if (!lifecycleAuditResponse.ok()) {
    throw new Error(
      `Lifecycle audit returned ` +
        `${lifecycleAuditResponse.status()}: ` +
        `${await lifecycleAuditResponse.text()}`,
    );
  }

  const lifecycleAuditBody =
    await lifecycleAuditResponse.json();
  const activationEvents = (
    lifecycleAuditBody.events || []
  ).filter(
    (event) => event.action === "ACTIVATE_PROJECT",
  );

  const initialActivationEvent = activationEvents.find(
    (event) => event.reason === activationReason,
  );
  const reactivationEvent = activationEvents.find(
    (event) => event.reason === reactivationReason,
  );
  const completionEvent = (
    lifecycleAuditBody.events || []
  ).find(
    (event) => event.action === "COMPLETE_PROJECT",
  );
  const archiveEvent = (
    lifecycleAuditBody.events || []
  ).find(
    (event) => event.action === "ARCHIVE_PROJECT",
  );
  const restoreEvent = (
    lifecycleAuditBody.events || []
  ).find(
    (event) => event.action === "RESTORE_PROJECT",
  );

  if (
    activationEvents.length !== 2 ||
    initialActivationEvent?.before_config?.status !==
      "PLANNED" ||
    initialActivationEvent?.after_config?.status !==
      "ACTIVE" ||
    initialActivationEvent?.config_patch
      ?.preflight_fingerprint !==
        preflightBody.decision.preflight_fingerprint ||
    reactivationEvent?.before_config?.status !==
      "PLANNED" ||
    reactivationEvent?.after_config?.status !== "ACTIVE" ||
    reactivationEvent?.config_patch
      ?.preflight_fingerprint !==
        reactivationPreflight.decision
          .preflight_fingerprint ||
    completionEvent?.before_config?.status !== "ACTIVE" ||
    completionEvent?.after_config?.status !== "COMPLETED" ||
    completionEvent?.reason !== completionReason ||
    completionEvent?.config_patch
      ?.preflight_fingerprint !==
        completionPreflightBody.decision
          .preflight_fingerprint ||
    archiveEvent?.before_config?.status !== "COMPLETED" ||
    archiveEvent?.after_config?.status !== "ARCHIVED" ||
    archiveEvent?.reason !== archiveReason ||
    archiveEvent?.config_patch?.preflight_fingerprint !==
      archivePreflightBody.decision.preflight_fingerprint ||
    restoreEvent?.before_config?.status !== "ARCHIVED" ||
    restoreEvent?.after_config?.status !== "COMPLETED" ||
    restoreEvent?.reason !== restoreReason ||
    restoreEvent?.config_patch?.preflight_fingerprint !==
      restorePreflightBody.decision.preflight_fingerprint ||
    restoreEvent?.config_patch?.restore_summary
      ?.prior_archive_event_id !== archiveEvent?.id
  ) {
    throw new Error(
      `Unexpected lifecycle audit: ` +
        `${JSON.stringify(lifecycleAuditBody)}`,
    );
  }

  await projectCard
    .getByRole("button", {
      name: "Scope history",
      exact: true,
    })
    .click();

  await projectCard
    .getByText(creationReason, { exact: true })
    .waitFor({ timeout: 30000 });

  await projectCard
    .getByText(villageName, { exact: false })
    .first()
    .waitFor({ timeout: 30000 });

  const auditResponse = await page.request.get(
    `${apiBaseUrl}/api/v1/projects/` +
      `${createdProject.id}/geography-scope/audit`,
    { headers },
  );

  if (!auditResponse.ok()) {
    throw new Error(
      `Scope history returned ${auditResponse.status()}: ` +
        `${await auditResponse.text()}`,
    );
  }

  const auditBody = await auditResponse.json();
  if (
    auditBody.count !== 1 ||
    auditBody.events?.[0]?.action !==
      "CREATE_PROJECT_GEOGRAPHY_SCOPE" ||
    auditBody.events?.[0]?.reason !== creationReason
  ) {
    throw new Error(
      `Unexpected creation audit: ${JSON.stringify(auditBody)}`,
    );
  }

  const screenshot = path.join(
    screenshotDir,
    "project-created-with-geography-scope.png",
  );

  await page.screenshot({
    path: screenshot,
    fullPage: true,
  });

  console.log(JSON.stringify({
    schema_version:
      "project_creation_geography_scope_web_smoke.v1",
    status: "PASSED",
    project_id: createdProject.id,
    project_name: fixtureName,
    village_lgd_code: villageLgdCode,
    village_name: villageName,
    geography_source:
      createdProject.geography_scope.source,
    persisted_scope_verified: true,
    creation_audit_verified: true,
    creation_history_ui_verified: true,
    activation_preflight_verified: true,
    activation_preflight_lazy_load_verified: true,
    activation_preflight_request_count:
      activationPreflightRequestCount,
    guarded_activation_verified: true,
    activation_reason_verified: true,
    activation_audit_verified: true,
    activation_fingerprint_verified: true,
    active_status_persisted_before_deactivation: true,
    lifecycle_history_verified: true,
    lifecycle_history_lazy_load_verified: true,
    lifecycle_history_request_count:
      lifecycleHistoryRequestCount,
    lifecycle_transition_verified: true,
    lifecycle_reason_verified: true,
    lifecycle_fingerprint_verified: true,
    deactivation_preflight_verified: true,
    deactivation_preflight_lazy_load_verified: true,
    deactivation_preflight_request_count:
      deactivationPreflightRequestCount,
    deactivation_operational_counts_verified: true,
    guarded_deactivation_verified: true,
    deactivation_reason_verified: true,
    deactivation_audit_verified: true,
    deactivation_fingerprint_verified: true,
    deactivation_runtime_guardrails_verified: true,
    planned_status_persisted_after_deactivation: true,
    lifecycle_deactivation_transition_verified: true,
    completion_preflight_verified: true,
    completion_preflight_lazy_load_verified: true,
    completion_preflight_request_count:
      completionPreflightRequestCount,
    guarded_completion_verified: true,
    completion_reason_verified: true,
    completion_audit_verified: true,
    completion_fingerprint_verified: true,
    completion_runtime_guardrails_verified: true,
    completed_status_persisted: true,
    lifecycle_completion_transition_verified: true,
    archive_preflight_verified: true,
    archive_preflight_lazy_load_verified: true,
    archive_preflight_request_count:
      archivePreflightRequestCount,
    guarded_archive_verified: true,
    archive_reason_verified: true,
    archive_audit_verified: true,
    archive_fingerprint_verified: true,
    archived_status_persisted: true,
    restore_preflight_verified: true,
    restore_preflight_lazy_load_verified: true,
    restore_preflight_request_count:
      restorePreflightRequestCount,
    guarded_restore_verified: true,
    restore_reason_verified: true,
    restore_audit_verified: true,
    restore_fingerprint_verified: true,
    completed_status_persisted_after_restore: true,
    archive_restore_runtime_guardrails_verified: true,
    lifecycle_archive_restore_transitions_verified: true,
    project_created_only_on_submit: true,
    screenshot,
    guardrails: {
      candidate_activation_changed: false,
      candidate_promotion_changed: false,
      runtime_lookup_enabled: false,
      android_behavior_changed: false,
    },
  }, null, 2));
} catch (error) {
  const screenshot = path.join(
    screenshotDir,
    "project-creation-geography-scope-failed.png",
  );

  await page.screenshot({
    path: screenshot,
    fullPage: true,
  }).catch(() => undefined);

  throw new Error(
    `${error instanceof Error ? error.message : String(error)}\n` +
      `URL: ${page.url()}\n` +
      `Screenshot: ${screenshot}\n` +
      `Page excerpt: ${(await page.locator("body").innerText()
        .catch(() => "")).slice(0, 5000)}\n` +
      `Browser events: ${JSON.stringify(browserEvents, null, 2)}`,
  );
} finally {
  await browser.close();
}
