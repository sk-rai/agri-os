import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const token = process.env.WEB_SWEEP_TOKEN;
const tenantId = process.env.WEB_SWEEP_TENANT_ID || "default";
const actorId = process.env.WEB_SWEEP_ACTOR_ID;

if (!token || !actorId) {
  console.error(
    "Missing WEB_SWEEP_TOKEN / WEB_SWEEP_ACTOR_ID. " +
    "Run run_core_layer_project_override_smoke.mjs.",
  );
  process.exit(1);
}

const webBaseUrl =
  process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl =
  process.env.WEB_API_BASE_URL || "http://127.0.0.1:8000";
const readinessUrl =
  `${webBaseUrl}/geography-layer-readiness`;

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const authHeaders = {
  Authorization: `Bearer ${token}`,
  "X-Tenant-ID": tenantId,
  "X-Actor-ID": actorId,
};

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1100 },
  extraHTTPHeaders: authHeaders,
});

await context.addInitScript(
  ({ token, tenantId, actorId }) => {
    window.localStorage.setItem("agrios_token", token);
    window.localStorage.setItem(
      "agrios_tenant_id",
      tenantId,
    );
    window.localStorage.setItem(
      "agrios_user_id",
      actorId,
    );
  },
  { token, tenantId, actorId },
);

const page = await context.newPage();
const browserEvents = [];
let appliedAssignment = null;
let rollbackCompleted = false;

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
  if (
    response.url().includes(
      "/core-layer-project-overrides/",
    ) ||
    response.url().includes(
      "/api/v1/master-data/geography/layer-readiness",
    )
  ) {
    browserEvents.push({
      type: "response",
      status: response.status(),
      method: response.request().method(),
      url: response.url(),
      text: (
        await response.text().catch(() => "")
      ).slice(0, 1200),
    });
  }
});

async function apiJson(relativeUrl, options = {}) {
  const response = await context.request.fetch(
    `${apiBaseUrl}${relativeUrl}`,
    {
      ...options,
      headers: {
        ...authHeaders,
        ...(options.headers || {}),
      },
    },
  );

  const text = await response.text();
  if (!response.ok()) {
    throw new Error(
      `API ${options.method || "GET"} ${relativeUrl} ` +
      `failed: ${response.status()} ${text.slice(0, 1000)}`,
    );
  }
  return text ? JSON.parse(text) : {};
}

async function findFixture() {
  const projects = await apiJson("/api/v1/projects");

  for (const project of projects) {
    const rawCodes =
      project?.geography_scope?.village_lgd_codes;
    const codes = Array.isArray(rawCodes)
      ? rawCodes.map(String).filter(Boolean).slice(0, 100)
      : [];

    if (!codes.length) continue;

    const params = new URLSearchParams({
      lgd_codes: codes.join(","),
    });
    const villages = await apiJson(
      `/api/v1/master-data/geography/villages/by-lgd-codes?${params.toString()}`,
    );

    for (const village of villages) {
      const endpoint =
        "/api/v1/master-data/geography/" +
        "core-layer-project-overrides/projects/" +
        `${project.id}/villages/${village.id}`;

      const response = await context.request.get(
        `${apiBaseUrl}${endpoint}`,
        { headers: authHeaders },
      );

      if (!response.ok()) continue;

      const assignmentContext = await response.json();
      if (
        assignmentContext.active_overrides.length === 0 &&
        assignmentContext.region_options.length > 0
      ) {
        return {
          project,
          village,
          endpoint,
          assignmentContext,
        };
      }
    }
  }

  throw new Error(
    "No project village without an existing Core override " +
    "and with available Core regions was found.",
  );
}

const fixture = await findFixture();

try {
  await page.goto(readinessUrl, {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });

  const corePanel = page.getByTestId(
    "core-layer-project-override-panel",
  );
  await corePanel.waitFor({ timeout: 60000 });

  await corePanel
    .getByRole("heading", {
      name: "Project-specific Core-layer overrides",
    })
    .waitFor({ timeout: 15000 });

  const projectSelect = corePanel.locator("select").first();

  await projectSelect.waitFor({ timeout: 30000 });
  await projectSelect.selectOption(fixture.project.id);

  const search = corePanel.getByRole("combobox", {
    name: "Search project village",
  });

  await search.waitFor({ timeout: 30000 });
  await page.waitForFunction(
    () => {
      const input = document.querySelector(
        "#core-project-village-search",
      );
      return Boolean(
        input &&
        !input.disabled &&
        !input.placeholder.includes("Loading"),
      );
    },
    null,
    { timeout: 30000 },
  );

  await search.fill(fixture.village.lgd_code);

  const villageOption = page.getByRole("option").filter({
    hasText: `LGD ${fixture.village.lgd_code}`,
  });
  await villageOption.first().waitFor({ timeout: 15000 });
  await villageOption.first().click();

  await page
    .getByText(
      `LGD ${fixture.village.lgd_code}`,
      { exact: false },
    )
    .first()
    .waitFor({ timeout: 15000 });

  await page
    .getByRole("button", {
      name: "Load Core-layer options",
    })
    .click();

  await page
    .getByRole("heading", {
      name: "Effective Core layers",
    })
    .waitFor({ timeout: 30000 });

  await page
    .getByText("0 project overrides", { exact: true })
    .waitFor({ timeout: 15000 });

  const dryRunButton = corePanel
    .getByRole("button", { name: "Dry run" })
    .first();

  const dryRunResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(fixture.endpoint) &&
      response.request().method() === "PUT" &&
      response.status() === 200,
    { timeout: 30000 },
  );

  await dryRunButton.click();
  const dryRunResponse = await dryRunResponsePromise;
  const dryRunPayload = await dryRunResponse.json();

  if (dryRunPayload.mode !== "DRY_RUN") {
    throw new Error(
      `Unexpected dry-run mode: ${dryRunPayload.mode}`,
    );
  }

  await page
    .getByText("Dry run:", { exact: false })
    .first()
    .waitFor({ timeout: 15000 });

  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });

  const applyResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(fixture.endpoint) &&
      response.request().method() === "PUT" &&
      response.status() === 200,
    { timeout: 30000 },
  );

  await corePanel
    .getByRole("button", {
      name: "Use for this project",
    })
    .first()
    .click();

  const applyResponse = await applyResponsePromise;
  const applyPayload = await applyResponse.json();

  if (
    applyPayload.mode !== "APPLY" ||
    !applyPayload.assignment
  ) {
    throw new Error(
      `Unexpected apply response: ${JSON.stringify(
        applyPayload,
      )}`,
    );
  }

  appliedAssignment = applyPayload.assignment;

  await page
    .getByText("1 project overrides", { exact: true })
    .waitFor({ timeout: 30000 });

  await page
    .getByText("Project override", { exact: true })
    .first()
    .waitFor({ timeout: 15000 });

  const effectiveAfterApply = await apiJson(
    `${fixture.endpoint}/effective`,
  );
  const appliedRegion = effectiveAfterApply.effective_regions.find(
    (row) =>
      row.region_system ===
      appliedAssignment.region_system,
  );

  if (
    !appliedRegion ||
    appliedRegion.resolution_source !== "PROJECT_OVERRIDE"
  ) {
    throw new Error(
      "Effective resolver did not expose the applied " +
      "project override.",
    );
  }

  await corePanel.screenshot({
    path: path.join(
      screenshotDir,
      "core-layer-project-override-applied.png",
    ),
    timeout: 60000,
  });

  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });

  const rollbackResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(fixture.endpoint) &&
      response.request().method() === "DELETE" &&
      response.status() === 200,
    { timeout: 30000 },
  );

  await corePanel
    .getByRole("button", { name: "Roll back" })
    .first()
    .click();

  const rollbackResponse = await rollbackResponsePromise;
  const rollbackPayload = await rollbackResponse.json();

  if (
    rollbackPayload.mode !== "ROLLBACK" ||
    rollbackPayload.action !== "ROLLED_BACK"
  ) {
    throw new Error(
      `Unexpected rollback response: ${JSON.stringify(
        rollbackPayload,
      )}`,
    );
  }

  rollbackCompleted = true;

  await page
    .getByText("0 project overrides", { exact: true })
    .waitFor({ timeout: 30000 });

  const effectiveAfterRollback = await apiJson(
    `${fixture.endpoint}/effective`,
  );
  const activeAfterRollback =
    effectiveAfterRollback.effective_regions.find(
      (row) =>
        row.region_system ===
          appliedAssignment.region_system &&
        row.resolution_source === "PROJECT_OVERRIDE",
    );

  if (activeAfterRollback) {
    throw new Error(
      "Project override remained effective after rollback.",
    );
  }

  await corePanel.screenshot({
    path: path.join(
      screenshotDir,
      "core-layer-project-override-rolled-back.png",
    ),
    timeout: 60000,
  });

  console.log(JSON.stringify({
    schema_version:
      "core_layer_project_override_web_smoke.v1",
    status: "PASSED",
    tenant_id: tenantId,
    project_id: fixture.project.id,
    project_name: fixture.project.name,
    village_id: fixture.village.id,
    village_lgd_code: fixture.village.lgd_code,
    village_name: fixture.village.canonical_name,
    region_system: appliedAssignment.region_system,
    applied_region_code:
      appliedAssignment.region_code,
    dry_run_mode: dryRunPayload.mode,
    apply_action: applyPayload.action,
    rollback_action: rollbackPayload.action,
    effective_source_after_apply:
      appliedRegion.resolution_source,
    effective_project_override_after_rollback: false,
    screenshots: [
      "web/smoke/screenshots/" +
        "core-layer-project-override-applied.png",
      "web/smoke/screenshots/" +
        "core-layer-project-override-rolled-back.png",
    ],
    browser_event_count: browserEvents.length,
  }, null, 2));
} catch (error) {
  await page.screenshot({
    path: path.join(
      screenshotDir,
      "core-layer-project-override-failed.png",
    ),
    fullPage: false,
    timeout: 10000,
  }).catch(() => {});

  throw new Error(
    `${error.message}
Browser events: ` +
    JSON.stringify(browserEvents, null, 2),
  );
} finally {
  if (appliedAssignment && !rollbackCompleted) {
    const params = new URLSearchParams({
      region_system: appliedAssignment.region_system,
      rollback_token: appliedAssignment.rollback_token,
    });

    const cleanupResponse = await context.request.delete(
      `${apiBaseUrl}${fixture.endpoint}?${params.toString()}`,
      { headers: authHeaders },
    );

    if (!cleanupResponse.ok()) {
      console.error(
        "Emergency rollback failed:",
        cleanupResponse.status(),
        await cleanupResponse.text(),
      );
    } else {
      console.warn(
        "Emergency rollback completed after smoke failure.",
      );
    }
  }

  await browser.close();
}
