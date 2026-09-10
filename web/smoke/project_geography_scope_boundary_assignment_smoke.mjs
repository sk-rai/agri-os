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
  process.env.WEB_SCOPE_PROJECT_NAME ||
  "NWDP Boundary Assignment Playwright Fixture";

const villageLgdCode =
  process.env.WEB_SCOPE_VILLAGE_LGD_CODE || "645063";
const villageName =
  process.env.WEB_SCOPE_VILLAGE_NAME || "Hoipoh*";
const villageSearch =
  process.env.WEB_SCOPE_VILLAGE_SEARCH || "Hoipoh";
const stateId =
  process.env.WEB_SCOPE_STATE_ID ||
  "c29469a4-5655-4385-8fbb-40d2fbcdd132";
const districtId =
  process.env.WEB_SCOPE_DISTRICT_ID ||
  "2fe15657-3321-41b5-8b9c-698afeab1632";

if (!token || !actorId) {
  throw new Error(
    "Missing WEB_SWEEP_TOKEN or WEB_SWEEP_ACTOR_ID. " +
      "Generate them with create_web_ui_smoke_session.py.",
  );
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1600, height: 1100 },
});

const browserEvents = [];

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

let project;
let scopeResponseBody;

try {
  const projectsResponse = await page.request.get(
    `${apiBaseUrl}/api/v1/projects`,
    { headers },
  );

  if (!projectsResponse.ok()) {
    throw new Error(
      `Project list returned ${projectsResponse.status()}: ` +
        `${await projectsResponse.text()}`,
    );
  }

  const projects = await projectsResponse.json();
  const matches = projects.filter(
    (item) =>
      item.name === fixtureName &&
      item.status === "PLANNED",
  );

  if (matches.length !== 1) {
    throw new Error(
      `Expected exactly one PLANNED project named "${fixtureName}", ` +
        `found ${matches.length}`,
    );
  }

  project = matches[0];

  await page.goto(`${baseUrl}/projects`, {
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });

  await page
    .getByRole("heading", { name: "Projects", exact: true })
    .waitFor({ timeout: 30000 });

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
    .getByRole("button", {
      name: "Geography scope",
      exact: true,
    })
    .click();

  const stateSelect = projectCard.getByLabel(
    "State / Union Territory",
  );
  await stateSelect.waitFor({ timeout: 30000 });
  await stateSelect.selectOption(stateId);

  const districtSelect = projectCard.getByLabel("District");
  await districtSelect.waitFor({ timeout: 30000 });
  await districtSelect.selectOption(districtId);

  const villageSearchInput = projectCard.getByLabel("Search villages");
  await villageSearchInput.fill(villageSearch);

  const villageResult = projectCard
    .getByLabel("Village search results")
    .getByRole("button")
    .filter({ hasText: `LGD ${villageLgdCode}` })
    .first();

  await villageResult.waitFor({ timeout: 30000 });
  await villageResult.click();

  await projectCard
    .getByText(`LGD ${villageLgdCode}`, { exact: false })
    .last()
    .waitFor({ timeout: 30000 });

  await projectCard
    .getByLabel("Change reason")
    .fill(
      "Playwright project scope followed by boundary assignment",
    );

  const [scopeResponse] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === "PATCH" &&
        response.url().endsWith(
          `/api/v1/projects/${project.id}/geography-scope`,
        ),
      { timeout: 30000 },
    ),
    projectCard
      .getByRole("button", {
        name: "Save geography scope",
        exact: true,
      })
      .click(),
  ]);

  scopeResponseBody = await scopeResponse.json().catch(async () => ({
    raw: await scopeResponse.text(),
  }));

  if (scopeResponse.status() !== 200) {
    throw new Error(
      `Scope PATCH returned ${scopeResponse.status()}: ` +
        `${JSON.stringify(scopeResponseBody)}`,
    );
  }

  const savedCodes =
    scopeResponseBody?.geography_scope?.village_lgd_codes || [];

  if (!savedCodes.includes(villageLgdCode)) {
    throw new Error(
      `Scope response does not contain LGD code ${villageLgdCode}`,
    );
  }

  await page.reload({
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });

  const reloadedCard = page
    .locator("div.bg-white.rounded-lg.shadow.p-4")
    .filter({
      has: page.getByRole("heading", {
        name: fixtureName,
        exact: true,
      }),
    })
    .first();

  await reloadedCard.waitFor({ timeout: 30000 });

  await reloadedCard
    .getByRole("button", {
      name: "Geography scope",
      exact: true,
    })
    .click();

  const persistedVillage = reloadedCard
    .getByText(`LGD ${villageLgdCode}`, { exact: false })
    .first();

  const persistedAfterReload =
    (await persistedVillage.count()) > 0 &&
    (await persistedVillage.isVisible());

  if (!persistedAfterReload) {
    throw new Error(
      `LGD code ${villageLgdCode} did not persist after reload`,
    );
  }

  const scopeScreenshot = path.join(
    screenshotDir,
    "project-geography-scope-persisted.png",
  );

  await page.screenshot({
    path: scopeScreenshot,
    fullPage: true,
  });

  console.log(
    JSON.stringify(
      {
        schema_version:
          "project_geography_scope_web_smoke.v1",
        status: "PASSED",
        project_id: project.id,
        project_name: project.name,
        village_lgd_code: villageLgdCode,
    village_name: villageName,
        scope_source:
          scopeResponseBody.geography_scope?.source,
        persisted_after_reload: true,
        screenshot: scopeScreenshot,
        guardrails: {
          candidate_activation_changed: false,
          candidate_promotion_changed: false,
          runtime_eligibility_changed: false,
          runtime_lookup_enabled: false,
          android_behavior_changed: false,
        },
      },
      null,
      2,
    ),
  );
} catch (error) {
  const screenshot = path.join(
    screenshotDir,
    "project-geography-scope-exercise-failed.png",
  );

  await page.screenshot({
    path: screenshot,
    fullPage: true,
  }).catch(() => {});

  const body = await page
    .locator("body")
    .innerText()
    .catch(() => "");

  throw new Error(
    `${error.message}\n` +
      `URL: ${page.url()}\n` +
      `Screenshot: ${screenshot}\n` +
      `Page excerpt: ${body.slice(0, 5000)}\n` +
      `Browser events: ${JSON.stringify(
        browserEvents.slice(-30),
        null,
        2,
      )}`,
  );
} finally {
  await browser.close();
}

process.env.WEB_PROJECT_ID = project.id;
process.env.WEB_SCOPE_VILLAGE_LGD_CODE = villageLgdCode;

await import("./nwdp_project_boundary_assignment_smoke.mjs");
