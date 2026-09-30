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
    "Run run_geography_layer_readiness_gated_smoke.mjs.",
  );
  process.exit(1);
}

const webBaseUrl =
  process.env.WEB_BASE_URL || "http://localhost:3000";
const readinessUrl =
  `${webBaseUrl}/geography-layer-readiness`;

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1100 },
  extraHTTPHeaders: {
    Authorization: `Bearer ${token}`,
    "X-Tenant-ID": tenantId,
    "X-Actor-ID": actorId,
  },
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
const readinessRequests = [];
const coverageRequests = [];
const browserEvents = [];

page.on("request", (request) => {
  const url = new URL(request.url());
  if (
    url.pathname ===
    "/api/v1/master-data/geography/layer-readiness"
  ) {
    readinessRequests.push(request.url());
  }
  if (
    url.pathname ===
    "/api/v1/master-data/geography/layer-readiness/" +
      "snapshot-coverage"
  ) {
    coverageRequests.push(request.url());
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

function nonEmptyOptions(select) {
  return select.locator("option").evaluateAll(
    (options) =>
      options
        .map((option) => ({
          value: option.value,
          label: option.textContent?.trim() || "",
        }))
        .filter((option) => option.value),
  );
}

try {
  await page.goto(readinessUrl, {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });

  const corePanel = page.getByTestId(
    "core-layer-project-override-panel",
  );
  await corePanel.waitFor({ timeout: 60000 });

  const filterPanel = page.getByTestId(
    "geography-readiness-filters",
  );
  await filterPanel.waitFor({ timeout: 30000 });

  const stateSelect = filterPanel.getByLabel("State / UT", {
    exact: true,
  });
  const districtSelect = filterPanel.getByLabel("District", {
    exact: true,
  });
  const loadButton = filterPanel.getByRole("button", {
    name: "Load readiness",
  });

  await stateSelect.waitFor({ timeout: 30000 });

  await page.waitForFunction(
    () => {
      const select = document.querySelector(
        'select[aria-label="State / UT"]',
      );
      return Boolean(
        select &&
        Array.from(select.options).some(
          (option) => Boolean(option.value),
        ),
      );
    },
    null,
    { timeout: 30000 },
  );

  if (readinessRequests.length !== 0) {
    throw new Error(
      "Readiness lookup ran before state and district selection: " +
      JSON.stringify(readinessRequests),
    );
  }

  if (!(await districtSelect.isDisabled())) {
    throw new Error(
      "District selector was enabled before selecting a state.",
    );
  }

  if (!(await loadButton.isDisabled())) {
    throw new Error(
      "Load readiness was enabled before selecting filters.",
    );
  }

  const stateOptions = await nonEmptyOptions(stateSelect);
  if (!stateOptions.length) {
    throw new Error("No canonical state options were loaded.");
  }

  const firstState = stateOptions[0];
  const coverageResponsePromise = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return (
        url.pathname ===
          "/api/v1/master-data/geography/layer-readiness/" +
            "snapshot-coverage" &&
        response.status() === 200
      );
    },
    { timeout: 30000 },
  );

  await stateSelect.selectOption(firstState.value);
  const coverageResponse = await coverageResponsePromise;
  const coveragePayload = await coverageResponse.json();

  if (
    coveragePayload.schema_version !==
    "geography_layer_readiness_snapshot_coverage.v1"
  ) {
    throw new Error(
      `Unexpected coverage schema: ${
        coveragePayload.schema_version
      }`,
    );
  }

  if (coverageRequests.length !== 1) {
    throw new Error(
      "Expected one snapshot coverage request, received " +
      `${coverageRequests.length}`,
    );
  }

  await page.waitForFunction(
    () => {
      const select = document.querySelector(
        'select[aria-label="District"]',
      );
      return Boolean(
        select &&
        !select.disabled &&
        Array.from(select.options).some(
          (option) => Boolean(option.value),
        ),
      );
    },
    null,
    { timeout: 30000 },
  );

  if (readinessRequests.length !== 0) {
    throw new Error(
      "Readiness lookup ran after state-only selection: " +
      JSON.stringify(readinessRequests),
    );
  }

  const districtOptions = await nonEmptyOptions(districtSelect);
  if (!districtOptions.length) {
    throw new Error(
      `No districts loaded for state ${firstState.label}.`,
    );
  }

  const firstDistrict = districtOptions[0];
  await districtSelect.selectOption(firstDistrict.value);

  if (readinessRequests.length !== 0) {
    throw new Error(
      "Readiness lookup ran before explicit load: " +
      JSON.stringify(readinessRequests),
    );
  }

  if (await loadButton.isDisabled()) {
    throw new Error(
      "Load readiness remained disabled after both selections.",
    );
  }

  const responsePromise = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return (
        url.pathname ===
          "/api/v1/master-data/geography/layer-readiness" &&
        response.request().method() === "GET" &&
        response.status() === 200
      );
    },
    { timeout: 120000 },
  );

  await loadButton.click();

  const response = await responsePromise;
  const responseUrl = new URL(response.url());
  const payload = await response.json();

  if (readinessRequests.length !== 1) {
    throw new Error(
      "Expected exactly one readiness request, received " +
      `${readinessRequests.length}: ` +
      JSON.stringify(readinessRequests),
    );
  }

  const expectedState = firstState.label.replace(
    /\s+\([^()]+\)$/,
    "",
  );
  const expectedDistrict = firstDistrict.label
    .replace(/\s+·\s+(AVAILABLE|STALE|MISSING|CHECKING)$/, "")
    .replace(/\s+\([^()]+\)$/, "");

  const actualFilters = {
    state_or_ut: responseUrl.searchParams.get("state_or_ut"),
    district: responseUrl.searchParams.get("district"),
    limit: responseUrl.searchParams.get("limit"),
  };

  if (
    actualFilters.state_or_ut !== expectedState ||
    actualFilters.district !== expectedDistrict ||
    actualFilters.limit !== "50"
  ) {
    throw new Error(
      "Unexpected readiness filters: " +
      JSON.stringify({
        expected: {
          state_or_ut: expectedState,
          district: expectedDistrict,
          limit: "50",
        },
        actual: actualFilters,
      }),
    );
  }

  if (
    payload.schema_version !==
    "geography_layer_readiness_matrix.v1"
  ) {
    throw new Error(
      `Unexpected readiness schema: ${payload.schema_version}`,
    );
  }

  if (!Array.isArray(payload.rows) || !payload.rows.length) {
    throw new Error(
      "Filtered readiness response returned no district row.",
    );
  }

  const mismatchedRows = payload.rows.filter(
    (row) =>
      row.state_or_ut !== expectedState ||
      row.district !== expectedDistrict,
  );
  if (mismatchedRows.length) {
    throw new Error(
      "Readiness response escaped the selected scope: " +
      JSON.stringify(mismatchedRows.slice(0, 3)),
    );
  }

  await page
    .getByRole("heading", {
      name: "State/district readiness matrix",
    })
    .waitFor({ timeout: 30000 });

  await page
    .getByText(expectedDistrict, { exact: true })
    .last()
    .waitFor({ timeout: 30000 });

  await page.screenshot({
    path: path.join(
      screenshotDir,
      "geography-layer-readiness-gated.png",
    ),
    fullPage: false,
    timeout: 60000,
  });

  const missingDistrict = districtOptions.find(
    (option) => option.label.endsWith("· MISSING"),
  );
  let missingDistrictBlocked = false;

  if (missingDistrict) {
    await districtSelect.selectOption(missingDistrict.value);

    await page
      .getByTestId(
        "geography-readiness-offline-refresh-required",
      )
      .waitFor({ timeout: 15000 });

    missingDistrictBlocked =
      (await loadButton.isDisabled()) &&
      readinessRequests.length === 1;

    if (!missingDistrictBlocked) {
      throw new Error(
        "Missing district allowed an interactive readiness request.",
      );
    }
  }

  let stateResetVerified = true;
  if (stateOptions.length > 1) {
    await stateSelect.selectOption(stateOptions[1].value);

    await page.waitForFunction(
      () => {
        const select = document.querySelector(
          'select[aria-label="District"]',
        );
        return Boolean(select && select.value === "");
      },
      null,
      { timeout: 15000 },
    );

    stateResetVerified =
      (await districtSelect.inputValue()) === "" &&
      readinessRequests.length === 1;

    if (!stateResetVerified) {
      throw new Error(
        "Changing state did not clear district/readiness state.",
      );
    }
  }

  console.log(JSON.stringify({
    schema_version:
      "geography_layer_readiness_gated_web_smoke.v1",
    status: "PASSED",
    tenant_id: tenantId,
    selected_state: expectedState,
    selected_district: expectedDistrict,
    readiness_request_count: readinessRequests.length,
    snapshot_coverage_request_count: coverageRequests.length,
    snapshot_coverage_summary: coveragePayload.summary,
    readiness_filters: actualFilters,
    response_row_count: payload.rows.length,
    missing_district_blocked: missingDistrictBlocked,
    state_change_reset_verified: stateResetVerified,
    read_only: true,
    screenshot:
      "web/smoke/screenshots/" +
      "geography-layer-readiness-gated.png",
    browser_event_count: browserEvents.length,
  }, null, 2));
} catch (error) {
  await page.screenshot({
    path: path.join(
      screenshotDir,
      "geography-layer-readiness-gated-failed.png",
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
  await browser.close();
}
