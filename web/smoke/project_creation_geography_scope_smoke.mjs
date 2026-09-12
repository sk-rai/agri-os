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

page.on("request", (request) => {
  if (
    request.method() === "GET" &&
    request.url().includes("/activation-preflight")
  ) {
    activationPreflightRequestCount += 1;
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

  await page
    .getByRole("button", { name: "+ New Project", exact: true })
    .click();

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

  if (
    activationEvents.length !== 1 ||
    activationEvents[0].reason !== activationReason ||
    activationEvents[0].before_config?.status !== "PLANNED" ||
    activationEvents[0].after_config?.status !== "ACTIVE" ||
    activationEvents[0].config_patch
      ?.preflight_fingerprint !==
        preflightBody.decision.preflight_fingerprint
  ) {
    throw new Error(
      `Unexpected activation audit: ` +
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
    active_status_persisted: true,
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
