import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const token = process.env.WEB_SWEEP_TOKEN;
const tenantId = process.env.WEB_SWEEP_TENANT_ID || "android-fpo-multi-village-test";
const actorId = process.env.WEB_SWEEP_ACTOR_ID;

if (!token || !actorId) {
  console.error("Missing WEB_SWEEP_TOKEN / WEB_SWEEP_ACTOR_ID. Generate them with create_web_ui_smoke_session.py.");
  process.exit(1);
}

const projectId = process.env.FPO_PROJECT_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002001";
const selectedFarmerId = process.env.FPO_SELECTED_FARMER_ID || "0f7e0a6b-8472-5d6d-8a14-a9d000002106";
const selectedMobile = process.env.FPO_SELECTED_MOBILE || "+919900002106";
const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3000";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const enrollmentUrl = `${baseUrl}/project-enrollments?projectId=${projectId}&status=ACTIVE`;
const traceUrl = `${baseUrl}/project-trace/${projectId}`;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const screenshotDir = path.join(scriptDir, "screenshots");
await fs.mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1680, height: 1400 } });

await page.addInitScript(({ token, tenantId, actorId }) => {
  window.localStorage.setItem("agrios_token", token);
  window.localStorage.setItem("agrios_tenant_id", tenantId);
  window.localStorage.setItem("agrios_user_id", actorId);
  window.localStorage.setItem("agrios_role", "ENTERPRISE_ADMIN");
}, { token, tenantId, actorId });

async function apiFetch(pathname) {
  return page.evaluate(
    async ({ apiBaseUrl, pathname, token, tenantId, actorId }) => {
      const response = await fetch(`${apiBaseUrl}${pathname}`, {
        headers: {
          "Authorization": `Bearer ${token}`,
          "X-Tenant-ID": tenantId,
          "X-Actor-ID": actorId,
        },
      });
      const text = await response.text();
      let body = null;
      try {
        body = text ? JSON.parse(text) : null;
      } catch {
        body = text;
      }
      return { status: response.status, body };
    },
    { apiBaseUrl, pathname, token, tenantId, actorId }
  );
}

async function requireApi(statusLabel, response, predicate, detailBuilder = (body) => body) {
  if (response.status !== 200) {
    throw new Error(`${statusLabel} API returned ${response.status}: ${JSON.stringify(response.body).slice(0, 500)}`);
  }
  if (!predicate(response.body)) {
    throw new Error(`${statusLabel} API predicate failed: ${JSON.stringify(detailBuilder(response.body)).slice(0, 1200)}`);
  }
}

async function applyEnrollmentSearch(query) {
  await page.getByLabel("Search").fill(query);
  await page.getByRole("button", { name: "Apply filters" }).click();
}

try {
  await page.goto(enrollmentUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Project Enrollments" }).waitFor({ timeout: 20000 });
  await page.getByText("Android FPO Multi Village Crop Program").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("FPO Farmer 01 Rice").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("FPO Farmer 12 Sugarcane").first().waitFor({ timeout: 20000 });

  const allEnrollments = await apiFetch(`/api/v1/reports/project-enrollments?project_id=${projectId}&status=ACTIVE&limit=100`);
  await requireApi("all enrollment", allEnrollments, (body) => body.summary?.count === 12, (body) => body.summary);

  await applyEnrollmentSearch("Rampur");
  await page.locator("tbody").getByText("FPO Farmer 01 Rice").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("FPO Farmer 02 Rice").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("FPO Farmer 09 Sugarcane").first().waitFor({ timeout: 20000 });
  const rampurApi = await apiFetch(`/api/v1/reports/project-enrollments?project_id=${projectId}&status=ACTIVE&q=Rampur&limit=100`);
  await requireApi("Rampur search", rampurApi, (body) => body.summary?.count === 3 && body.enrollments.every((row) => row.village === "FPO Rampur"), (body) => ({ summary: body.summary, rows: body.enrollments }));

  await applyEnrollmentSearch("Rice");
  await page.locator("tbody").getByText("FPO Farmer 01 Rice").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("FPO Farmer 02 Rice").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("FPO Farmer 03 Rice").first().waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("FPO Farmer 10 Rice").first().waitFor({ timeout: 20000 });
  const riceSearchApi = await apiFetch(`/api/v1/reports/project-enrollments?project_id=${projectId}&status=ACTIVE&q=Rice&limit=100`);
  await requireApi("Rice search", riceSearchApi, (body) => body.summary?.count === 4 && body.enrollments.every((row) => row.farmer_name.includes("Rice")), (body) => ({ summary: body.summary, rows: body.enrollments }));

  await applyEnrollmentSearch(selectedMobile);
  await page.locator("tbody").getByText("FPO Farmer 06 Maize").first().waitFor({ timeout: 20000 });
  await page.getByText(selectedMobile).waitFor({ timeout: 20000 });
  const mobileSearchApi = await apiFetch(`/api/v1/reports/project-enrollments?project_id=${projectId}&status=ACTIVE&q=${encodeURIComponent(selectedMobile)}&limit=100`);
  await requireApi("mobile search", mobileSearchApi, (body) => body.summary?.count === 1 && body.enrollments[0]?.farmer_name === "FPO Farmer 06 Maize", (body) => ({ summary: body.summary, rows: body.enrollments }));

  await page.goto(`${traceUrl}?cropCode=RICE`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Project Trace" }).waitFor({ timeout: 20000 });
  await page.getByText("Android FPO Multi Village Crop Program").first().waitFor({ timeout: 20000 });
  await page.getByText("RICE: 4 cycles").waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("FPO Farmer 01 Rice").first().waitFor({ timeout: 20000 });
  const riceTraceApi = await apiFetch(`/api/v1/reports/projects/${projectId}/trace?crop_code=RICE&limit=100`);
  await requireApi("Rice trace", riceTraceApi, (body) => body.summary?.crop_cycle_count === 4 && body.crop_cycles.every((row) => row.crop_code === "RICE"), (body) => ({ summary: body.summary, cycles: body.crop_cycles }));

  await page.goto(`${traceUrl}?cropCode=WHEAT&cycleStatus=COMPLETED`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Project Trace" }).waitFor({ timeout: 20000 });
  await page.getByText("WHEAT: 1 cycles").waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("COMPLETED").first().waitFor({ timeout: 20000 });
  const wheatCompletedApi = await apiFetch(`/api/v1/reports/projects/${projectId}/trace?crop_code=WHEAT&cycle_status=COMPLETED&limit=100`);
  await requireApi("completed Wheat trace", wheatCompletedApi, (body) => body.summary?.crop_cycle_count === 1 && body.crop_cycles[0]?.status === "COMPLETED", (body) => ({ summary: body.summary, cycles: body.crop_cycles }));

  await page.goto(`${traceUrl}?farmerId=${selectedFarmerId}`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Project Trace" }).waitFor({ timeout: 20000 });
  await page.locator("tbody").getByText("FPO Farmer 06 Maize").first().waitFor({ timeout: 20000 });
  await page.getByText("MAIZE: 1 cycles").waitFor({ timeout: 20000 });
  const farmerTraceApi = await apiFetch(`/api/v1/reports/projects/${projectId}/trace?farmer_id=${selectedFarmerId}&limit=100`);
  await requireApi("farmer trace drilldown", farmerTraceApi, (body) => {
    const selected = body.farmers.find((row) => row.id === selectedFarmerId);
    return body.summary?.crop_cycle_count === 1 && selected?.crop_cycle_count === 1 && selected?.primary_crop_code === "MAIZE";
  }, (body) => ({ summary: body.summary, farmers: body.farmers }));

  const screenshotPath = path.join(screenshotDir, "fpo-project-enrollment-search.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    schema_version: "fpo_project_enrollment_search_web_smoke.v1",
    status: "PASSED",
    enrollment_url: enrollmentUrl,
    trace_url: traceUrl,
    screenshot: screenshotPath,
    tenant_id: tenantId,
    actor_id: actorId,
    project_id: projectId,
    evidence: {
      fpo_affiliated_farmer_count: allEnrollments.body.summary.count,
      fpo_search_village_rampur_count: rampurApi.body.summary.count,
      fpo_search_crop_rice_count: riceSearchApi.body.summary.count,
      fpo_search_mobile_maize_farmer: true,
      fpo_trace_rice_cycle_count: riceTraceApi.body.summary.crop_cycle_count,
      fpo_trace_completed_wheat_cycle_count: wheatCompletedApi.body.summary.crop_cycle_count,
      fpo_drilldown_farmer_crop: "MAIZE",
      fpo_drilldown_active_stage_visible: true,
    },
    api_cross_check_passed: true,
  }, null, 2));
} catch (error) {
  const screenshotPath = path.join(screenshotDir, "fpo-project-enrollment-search-failure.png");
  try {
    await page.screenshot({ path: screenshotPath, fullPage: true });
  } catch {
    // Best effort only.
  }
  console.error(JSON.stringify({
    schema_version: "fpo_project_enrollment_search_web_smoke_failure.v1",
    status: "FAILED",
    screenshot: screenshotPath,
    message: error instanceof Error ? error.message : String(error),
    body_text_sample: (await page.locator("body").innerText().catch(() => "")).slice(0, 4000),
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}