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
let readinessRequestCount = 0;
let projectCardPreviewRequestCount = 0;

page.on("request", (request) => {
  const url = request.url();
  if (url.includes("/project-geography-readiness")) {
    readinessRequestCount += 1;
  }
  if (
    url.includes(
      "/nwdp-boundary-project-matching/project-preview",
    ) &&
    url.includes("limit=1")
  ) {
    projectCardPreviewRequestCount += 1;
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

  try {
    await projectCard.waitFor({ timeout: 30000 });
  } catch {
    const body = await page.locator("body").innerText().catch(() => "");
    if (!body.includes("Loading...")) throw new Error(
      `Fixture project card did not render: ${body.slice(-1000)}`,
    );

    await page.reload({
      waitUntil: "domcontentloaded",
      timeout: 45000,
    });
    await page
      .getByRole("heading", { name: "Projects", exact: true })
      .waitFor({ timeout: 30000 });
    await projectCard.waitFor({ timeout: 30000 });
  }

  await projectCard
    .getByRole("button", {
      name: "Geography scope",
      exact: true,
    })
    .click();

  const stateSelect = projectCard.getByLabel(
    "State / Union Territory",
  );
  await stateSelect.selectOption(stateId);

  const districtSelect = projectCard.getByLabel(
    "District",
    { exact: true },
  );
  await districtSelect.locator(
    `option[value="${districtId}"]`,
  ).waitFor({
    state: "attached",
    timeout: 30000,
  });

  const [blocksResponse] = await Promise.all([
    page.waitForResponse(
      (response) => {
        const url = new URL(response.url());
        return (
          url.pathname.endsWith(
            "/api/v1/master-data/geography/blocks",
          ) &&
          url.searchParams.get("district_id") === districtId
        );
      },
      { timeout: 30000 },
    ),
    districtSelect.selectOption(districtId),
  ]);
  if (blocksResponse.status() !== 200) {
    throw new Error(
      `Block list returned ${blocksResponse.status()}`,
    );
  }

  const blockSelect = projectCard.getByLabel(
    "Block / Sub-district",
  );
  const nancowryOption = blockSelect
    .locator("option")
    .filter({ hasText: "Nancowry" })
    .first();

  await nancowryOption.waitFor({
    state: "attached",
    timeout: 30000,
  });

  const nancowryBlockId = await nancowryOption.getAttribute("value");
  if (!nancowryBlockId) {
    throw new Error("Nancowry block option has no value");
  }
  await blockSelect.selectOption(nancowryBlockId);

  const blockPreviewResponsePromise = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return (
        url.pathname.endsWith(
          "/api/v1/master-data/geography/" +
            "villages/bulk-selection-preview",
        ) &&
        url.searchParams.get("block_id") === nancowryBlockId
      );
    },
    { timeout: 30000 },
  );

  await projectCard
    .getByRole("button", {
      name: "Preview block villages",
      exact: true,
    })
    .click();

  const blockPreviewResponse = await blockPreviewResponsePromise;
  const blockPreviewData = await blockPreviewResponse.json();

  if (blockPreviewResponse.status() !== 200) {
    throw new Error(
      `Block preview returned ${blockPreviewResponse.status()}: ` +
        `${JSON.stringify(blockPreviewData)}`,
    );
  }

  if (
    blockPreviewData.scope?.scope_type !== "BLOCK" ||
    blockPreviewData.scope?.scope_name !== "Nancowry" ||
    blockPreviewData.summary?.total_village_count < 1 ||
    blockPreviewData.summary?.can_select_entire_scope !== true
  ) {
    throw new Error(
      `Unexpected Nancowry block preview: ` +
        `${JSON.stringify(blockPreviewData)}`,
    );
  }

  const bulkPreviewPanel = projectCard.getByLabel(
    "Bulk village selection preview",
  );
  await bulkPreviewPanel.waitFor({ timeout: 30000 });

  await bulkPreviewPanel
    .getByText(
      `${blockPreviewData.summary.total_village_count} canonical villages`,
      { exact: true },
    )
    .waitFor({ timeout: 30000 });

  await bulkPreviewPanel
    .getByText("Already selected", { exact: false })
    .waitFor({ timeout: 30000 });

  const confirmBulkButton = bulkPreviewPanel.getByRole(
    "button",
    {
      name:
        `Confirm add ${blockPreviewData.summary.total_village_count} villages`,
      exact: true,
    },
  );

  if (await confirmBulkButton.isDisabled()) {
    throw new Error(
      "Selectable Nancowry block confirmation is disabled",
    );
  }

  await confirmBulkButton.click();

  await projectCard
    .getByText(
      `Selected villages (${blockPreviewData.summary.total_village_count}/500)`,
      { exact: true },
    )
    .waitFor({ timeout: 30000 });

  const projectListAfterClientSelection =
    await page.request.get(`${apiBaseUrl}/api/v1/projects`, {
      headers,
    });
  if (!projectListAfterClientSelection.ok()) {
    throw new Error(
      "Could not verify preview-only project state",
    );
  }

  const persistedProjects =
    await projectListAfterClientSelection.json();
  const persistedProject = persistedProjects.find(
    (item) => item.id === project.id,
  );
  const persistedPreviewCodes =
    persistedProject?.geography_scope?.village_lgd_codes || [];

  if (persistedPreviewCodes.length !== 0) {
    throw new Error(
      "Bulk preview/selection wrote project geography scope before Save",
    );
  }

  await projectCard
    .getByRole("button", {
      name: "Remove all",
      exact: true,
    })
    .click();
  await projectCard
    .getByRole("button", {
      name: "Confirm remove all",
      exact: true,
    })
    .click();

  await projectCard
    .getByText("Selected villages (0/500)", { exact: true })
    .waitFor({ timeout: 30000 });

  const csvInput = projectCard.getByLabel(
    "Import village scope CSV",
  );

  const invalidPreviewResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(
        `/api/v1/projects/${project.id}/geography-scope/import-preview`,
      ),
    { timeout: 30000 },
  );

  await csvInput.setInputFiles({
    name: "project-geography-invalid.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "village_lgd_code\n" +
        `${villageLgdCode}\n` +
        `${villageLgdCode}\n` +
        "not-an-lgd-code\n" +
        "999999999\n",
    ),
  });

  const invalidPreview = await invalidPreviewResponse;
  if (invalidPreview.status() !== 200) {
    throw new Error(
      `Invalid CSV preview returned ${invalidPreview.status()}`,
    );
  }

  await projectCard
    .getByText("Duplicate codes ignored (1)", { exact: true })
    .waitFor({ timeout: 30000 });
  await projectCard
    .getByText("Malformed codes (1)", { exact: true })
    .waitFor({ timeout: 30000 });
  await projectCard
    .getByText("Unknown canonical villages (1)", { exact: true })
    .waitFor({ timeout: 30000 });

  const invalidUseButton = projectCard.getByRole("button", {
    name: "Use 1 accepted villages",
    exact: true,
  });
  if (!(await invalidUseButton.isDisabled())) {
    throw new Error(
      "Invalid geography CSV unexpectedly allowed apply",
    );
  }

  const validPreviewResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(
        `/api/v1/projects/${project.id}/geography-scope/import-preview`,
      ),
    { timeout: 30000 },
  );

  await csvInput.setInputFiles({
    name: "project-geography-valid.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      `village_lgd_code\n${villageLgdCode}\n`,
    ),
  });

  const validPreview = await validPreviewResponse;
  if (validPreview.status() !== 200) {
    throw new Error(
      `Valid CSV preview returned ${validPreview.status()}`,
    );
  }

  await projectCard
    .getByText(villageName, { exact: true })
    .last()
    .waitFor({ timeout: 30000 });
  await projectCard
    .getByText("Andaman And Nicobar Islands / Nicobars / Nancowry", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  await projectCard
    .getByRole("button", {
      name: "Use 1 accepted villages",
      exact: true,
    })
    .click();

  await projectCard
    .getByText("Selected villages (1/500)", { exact: true })
    .waitFor({ timeout: 30000 });

  const selectedFilter = projectCard.getByLabel(
    "Filter selected villages",
  );
  await selectedFilter.fill("definitely-not-this-village");
  await projectCard
    .getByText("No selected villages match this filter.", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });
  await selectedFilter.fill("");

  await projectCard
    .getByRole("button", {
      name: "Remove all",
      exact: true,
    })
    .click();
  await projectCard
    .getByRole("button", {
      name: "Confirm remove all",
      exact: true,
    })
    .waitFor({ timeout: 30000 });
  await projectCard
    .getByRole("button", {
      name: "Cancel",
      exact: true,
    })
    .first()
    .click();

  await projectCard
    .getByRole("button", {
      name: `Remove village LGD ${villageLgdCode}`,
    })
    .waitFor({ timeout: 30000 });

  await projectCard
    .getByRole("button", {
      name: "Remove all",
      exact: true,
    })
    .click();
  await projectCard
    .getByRole("button", {
      name: "Confirm remove all",
      exact: true,
    })
    .click();

  await projectCard
    .getByText("Selected villages (0/500)", { exact: true })
    .waitFor({ timeout: 30000 });

  const existingVillageSelection = projectCard.getByRole(
    "button",
    { name: `Remove village LGD ${villageLgdCode}` },
  );

  if ((await existingVillageSelection.count()) === 0) {
    await projectCard
      .getByRole("button", {
        name: "Search across India",
        exact: true,
      })
      .click();

    const searchInput = projectCard.getByLabel("Search villages");

    const staleNameRequest = page.waitForRequest(
      (request) => {
        const url = new URL(request.url());
        return (
          url.pathname.endsWith(
            "/api/v1/master-data/geography/villages/search",
          ) &&
          url.searchParams.get("q") === villageSearch &&
          !url.searchParams.has("district_id")
        );
      },
      { timeout: 30000 },
    );

    await searchInput.fill(villageSearch);
    await staleNameRequest;

    const lgdSearchResponse = page.waitForResponse(
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

    const searchResponse = await lgdSearchResponse;
    if (searchResponse.status() !== 200) {
      throw new Error(
        `LGD village search returned ${searchResponse.status()}`,
      );
    }

    const villageResult = projectCard
      .getByLabel("Village search results")
      .getByRole("option")
      .filter({ hasText: `LGD ${villageLgdCode}` })
      .first();

    await villageResult.waitFor({ timeout: 30000 });

    const resultText = await villageResult.innerText();
    if (
      !resultText.includes("Andaman And Nicobar Islands") ||
      !resultText.includes("Nicobars") ||
      !resultText.includes("Nancowry")
    ) {
      throw new Error(
        `Global result is missing hierarchy labels: ${resultText}`,
      );
    }
    if (!resultText.includes("EXACT LGD")) {
      throw new Error(
        `Exact LGD result is missing its match label: ${resultText}`,
      );
    }

    await projectCard
      .getByRole("button", {
        name: "Select all displayed",
        exact: true,
      })
      .click();

    await projectCard
      .getByText("Selected villages (1/500)", { exact: true })
      .waitFor({ timeout: 30000 });

    await projectCard
      .getByRole("button", {
        name: `Remove village LGD ${villageLgdCode}`,
      })
      .waitFor({ timeout: 30000 });
  } else {
    await existingVillageSelection.waitFor({ timeout: 30000 });
  }

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

  const persistedVillageName = reloadedCard
    .getByText(villageName, { exact: false })
    .first();
  await persistedVillageName.waitFor({ timeout: 30000 });

  const persistedVillageCode = reloadedCard
    .getByText(`LGD ${villageLgdCode}`, { exact: false })
    .first();
  await persistedVillageCode.waitFor({ timeout: 30000 });

  const persistedAfterReload =
    await persistedVillageName.isVisible() &&
    await persistedVillageCode.isVisible();

  if (!persistedAfterReload) {
    throw new Error(
      `LGD code ${villageLgdCode} did not persist after reload`,
    );
  }

  const downloadPromise = page.waitForEvent("download", {
    timeout: 30000,
  });

  await reloadedCard
    .getByRole("button", {
      name: "Export current scope CSV",
      exact: true,
    })
    .click();

  const exportDownload = await downloadPromise;
  const exportPath = await exportDownload.path();
  if (!exportPath) {
    throw new Error("CSV export did not produce a local file");
  }

  const exportedCsv = await fs.readFile(exportPath, "utf-8");
  if (
    !exportedCsv.includes("village_lgd_code") ||
    !exportedCsv.includes(villageLgdCode) ||
    !exportedCsv.includes(villageName)
  ) {
    throw new Error(
      `Exported geography CSV is incomplete: ${exportedCsv}`,
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

  const geographySummary = reloadedCard.getByLabel(
    "Project geography summary",
  );
  await geographySummary.waitFor({ timeout: 30000 });

  await geographySummary
    .getByText("1 of 1 villages have an eligible boundary", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  await geographySummary
    .getByText("1 state · 1 district · 0 missing", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  const auditResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().includes(
        `/api/v1/projects/${project.id}/geography-scope/audit`,
      ),
    { timeout: 30000 },
  );

  await reloadedCard
    .getByRole("button", {
      name: "Scope history",
      exact: true,
    })
    .click();

  const auditResponse = await auditResponsePromise;
  if (auditResponse.status() !== 200) {
    throw new Error(
      `Geography scope audit returned ${auditResponse.status()}: ` +
        `${await auditResponse.text()}`,
    );
  }

  const auditPanel = reloadedCard.getByLabel(
    "Project geography scope history",
  );
  await auditPanel.waitFor({ timeout: 30000 });

  await auditPanel
    .getByText(
      "Playwright project scope followed by boundary assignment",
      { exact: true },
    )
    .waitFor({ timeout: 30000 });

  await auditPanel
    .getByText(`LGD ${villageLgdCode}`, { exact: false })
    .first()
    .waitFor({ timeout: 30000 });

  await auditPanel
    .getByText("ADDED", { exact: true })
    .first()
    .waitFor({ timeout: 30000 });

  await auditPanel
    .getByText("ELIGIBLE", { exact: true })
    .first()
    .waitFor({ timeout: 30000 });

  const changeFilter = auditPanel.getByLabel(
    "Village change filter",
  );
  await changeFilter.selectOption("REMOVED");
  await auditPanel
    .getByText("No audit changes match these filters.", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  await changeFilter.selectOption("ADDED");
  await auditPanel
    .getByText("ADDED", { exact: true })
    .first()
    .waitFor({ timeout: 30000 });

  const boundaryFilter = auditPanel.getByLabel(
    "Boundary readiness filter",
  );
  await boundaryFilter.selectOption("MISSING");
  await auditPanel
    .getByText("No audit changes match these filters.", {
      exact: true,
    })
    .waitFor({ timeout: 30000 });

  await boundaryFilter.selectOption("ELIGIBLE");
  await auditPanel
    .getByText("ELIGIBLE", { exact: true })
    .first()
    .waitFor({ timeout: 30000 });

  if (readinessRequestCount < 1) {
    throw new Error(
      "Projects page did not request batched geography readiness",
    );
  }

  if (projectCardPreviewRequestCount !== 0) {
    throw new Error(
      `Projects page made ${projectCardPreviewRequestCount} ` +
        "per-card boundary preview request(s)",
    );
  }

  const reviewBoundariesLink = geographySummary.getByRole("link", {
    name: "Review boundaries",
    exact: true,
  });
  const reviewHref = await reviewBoundariesLink.getAttribute("href");

  if (
    reviewHref !==
    `/nwdp-boundary-review?project_id=${project.id}#project-coverage-preview`
  ) {
    throw new Error(
      `Unexpected project boundary-review link: ${reviewHref}`,
    );
  }

  await Promise.all([
    page.waitForURL(
      (url) =>
        url.pathname === "/nwdp-boundary-review" &&
        url.searchParams.get("project_id") === project.id,
      { timeout: 30000 },
    ),
    reviewBoundariesLink.click(),
  ]);

  const projectPreviewSection = page.locator(
    "#project-coverage-preview",
  );
  await projectPreviewSection.waitFor({ timeout: 30000 });

  const deepLinkedProjectSelect = projectPreviewSection
    .getByLabel("Project");

  const deepLinkedProjectOption = deepLinkedProjectSelect.locator(
    `option[value="${project.id}"]:checked`,
  );
  await deepLinkedProjectOption.waitFor({
    state: "attached",
    timeout: 30000,
  });

  const deepLinkedProjectId = await deepLinkedProjectSelect.inputValue();

  if (deepLinkedProjectId !== project.id) {
    throw new Error(
      `Boundary review selected ${deepLinkedProjectId}; expected ${project.id}`,
    );
  }

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
    geography_summary_verified: true,
    boundary_review_deep_link_verified: true,
    geography_scope_audit_verified: true,
    geography_scope_audit_filters_verified: true,
    block_bulk_preview_verified: true,
    block_bulk_selection_verified: true,
    bulk_selection_preview_write_count: 0,
    nationwide_village_name_search_verified: true,
    nationwide_result_hierarchy_verified: true,
    exact_lgd_search_verified: true,
    keyboard_selection_verified: true,
    csv_invalid_preview_verified: true,
    csv_valid_preview_verified: true,
    csv_export_verified: true,
    bulk_selection_verified: true,
    selected_village_filter_verified: true,
    guarded_remove_all_verified: true,
    rapid_search_replacement_verified: true,
    batched_readiness_request_verified: true,
    per_card_preview_request_count: projectCardPreviewRequestCount,
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
