#!/usr/bin/env node
/**
 * Read-only admin/web smoke screenshot sweep.
 *
 * Visits known web routes, captures screenshots, records console/network/page
 * errors, and continues after failures. Exits 0 by default; pass
 * --fail-on-error to make CI fail on detected problems.
 */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const ROUTES = [
  { path: "/", label: "home" },
  { path: "/login", label: "login" },
  { path: "/dashboard", label: "dashboard" },
  { path: "/activity-usage", label: "activity_usage" },
  { path: "/agent-profiles", label: "agent_profiles" },
  { path: "/broadcasts", label: "broadcasts" },
  { path: "/company-discovery", label: "company_discovery" },
  { path: "/company-profile", label: "company_profile" },
  { path: "/conflicts", label: "conflicts" },
  { path: "/crop-taxonomy", label: "crop_taxonomy" },
  { path: "/field-agent-worklist", label: "field_agent_worklist" },
  { path: "/field-events", label: "field_events" },
  { path: "/inputs", label: "inputs" },
  { path: "/lookup", label: "lookup" },
  { path: "/my-access", label: "my_access" },
  { path: "/products", label: "products" },
  { path: "/profile-forms", label: "profile_forms" },
  { path: "/profile-readiness", label: "profile_readiness" },
  { path: "/project-enrollments", label: "project_enrollments" },
  { path: "/project-inputs", label: "project_inputs" },
  { path: "/project-workflows", label: "project_workflows" },
  { path: "/projects", label: "projects" },
  { path: "/query-threads", label: "query_threads" },
  { path: "/soil-enrichment", label: "soil_enrichment" },
  { path: "/sync-health", label: "sync_health" },
  { path: "/tenants", label: "tenants" },
  { path: "/users", label: "users" },
  { path: "/weather", label: "weather" },
  { path: "/workflows", label: "workflows" },
];

function argValue(name, fallback) {
  const prefix = `${name}=`;
  const found = process.argv.find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

function hasArg(name) {
  return process.argv.includes(name);
}


function isExpectedAuthOrPermissionResponse(response) {
  if (![400, 401, 403].includes(response.status)) return false;
  try {
    const url = new URL(response.url);
    if (!url.pathname.startsWith("/api/")) return false;
    return true;
  } catch {
    return false;
  }
}

function isIgnorableNavigationAbort(request) {
  if (request.failure !== "net::ERR_ABORTED" || request.method !== "GET") return false;
  try {
    const url = new URL(request.url);
    if (url.pathname === "/login") return true;
    if (url.hostname === "localhost" && url.port === "8000" && url.pathname.startsWith("/api/")) return true;
    if (url.hostname === "127.0.0.1" && url.port === "8000" && url.pathname.startsWith("/api/")) return true;
    return false;
  } catch {
    return false;
  }
}

function isGenericResourceConsoleError(error) {
  return error.type === "console" && String(error.message || "").includes("Failed to load resource:");
}

function classifyRouteStatus({ httpStatus, errors, failedRequests, responses }) {
  const unexpectedHttpErrors = responses.filter((response) => !isExpectedAuthOrPermissionResponse(response));
  const unexpectedFailedRequests = failedRequests.filter((request) => !isIgnorableNavigationAbort(request));
  const nonResourceConsoleErrors = errors.filter((error) => !isGenericResourceConsoleError(error));

  if (httpStatus && httpStatus >= 400) return "HTTP_ERROR";
  if (unexpectedHttpErrors.length || unexpectedFailedRequests.length || nonResourceConsoleErrors.length) return "HAS_ERRORS";
  if (responses.length || failedRequests.length || errors.length) return "EXPECTED_AUTH_OR_PERMISSION";
  return "OK";
}


function slug(value) {
  return String(value).replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "").toLowerCase();
}


async function cleanupOldRuns(outRoot, keepRuns, activeOutDir) {
  if (!Number.isFinite(keepRuns) || keepRuns < 0) return;
  let entries = [];
  try {
    entries = await fs.readdir(outRoot, { withFileTypes: true });
  } catch {
    return;
  }
  const dirs = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.resolve(outRoot, entry.name))
    .sort()
    .reverse();

  const active = path.resolve(activeOutDir);
  const retained = new Set(dirs.slice(0, keepRuns));
  retained.add(active);

  for (const dir of dirs) {
    if (retained.has(dir)) continue;
    await fs.rm(dir, { recursive: true, force: true }).catch(() => {});
  }
}


async function main() {
  const baseUrl = (argValue("--base-url", process.env.WEB_BASE_URL || "http://127.0.0.1:3000") || "").replace(/\/$/, "");
  const outRoot = argValue("--out", process.env.WEB_SWEEP_OUT || "test-artifacts/admin-smoke");
  const failOnError = hasArg("--fail-on-error");
  const headed = hasArg("--headed");
  const routeFilter = argValue("--route", "");
  const waitMs = Number(argValue("--settle-ms", "1200"));
  const keepRuns = Number(argValue("--keep-runs", process.env.WEB_SWEEP_KEEP_RUNS || "3"));
  const tenantId = argValue("--tenant-id", process.env.WEB_SWEEP_TENANT_ID || "default");
  const actorId = argValue("--actor-id", process.env.WEB_SWEEP_ACTOR_ID || "");
  const token = argValue("--token", process.env.WEB_SWEEP_TOKEN || "");

  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch (error) {
    console.error(JSON.stringify({
      schema_version: "admin_smoke_screenshot_sweep.v1",
      status: "PLAYWRIGHT_MISSING",
      message: "Install Playwright first: cd web && npm install -D playwright && npx playwright install chromium",
      error: String(error?.message || error),
    }, null, 2));
    process.exit(2);
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const outDir = path.resolve(outRoot, stamp);
  const screenshotDir = path.join(outDir, "screenshots");
  await fs.mkdir(screenshotDir, { recursive: true });
  await cleanupOldRuns(path.resolve(outRoot), keepRuns, outDir);

  let browser;
  try {
    browser = await chromium.launch({ headless: !headed });
  } catch (error) {
    const message = String(error?.message || error);
    const dependencyHint = message.includes("libasound.so.2")
      ? "Missing WSL/Linux browser dependency libasound.so.2. Run: sudo apt-get update && sudo apt-get install -y libasound2"
      : "Chromium could not launch. Run: npx playwright install-deps chromium";
    const summary = {
      schema_version: "admin_smoke_screenshot_sweep.v1",
      status: "BROWSER_LAUNCH_FAILED",
      generated_at: new Date().toISOString(),
      base_url: baseUrl,
      out_dir: outDir,
      issue_count: 1,
      error: message,
      dependency_hint: dependencyHint,
    };
    await fs.writeFile(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));
    await fs.writeFile(path.join(outDir, "summary.md"), [
      "# Admin Smoke Screenshot Sweep",
      "",
      "Status: BROWSER_LAUNCH_FAILED",
      "",
      dependencyHint,
      "",
      "```",
      message.slice(0, 4000),
      "```",
      "",
    ].join("\n"));
    console.error(JSON.stringify(summary, null, 2));
    process.exit(failOnError ? 1 : 0);
  }

  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    ignoreHTTPSErrors: true,
  });

  await context.addInitScript(({ tenantId, actorId, token }) => {
    if (tenantId) window.localStorage.setItem("agrios_tenant_id", tenantId);
    if (actorId) window.localStorage.setItem("agrios_user_id", actorId);
    if (token) window.localStorage.setItem("agrios_token", token);
  }, { tenantId, actorId, token });

  const selectedRoutes = routeFilter
    ? ROUTES.filter((route) => route.path.includes(routeFilter) || route.label.includes(routeFilter))
    : ROUTES;

  const results = [];

  for (const route of selectedRoutes) {
    const url = `${baseUrl}${route.path}`;
    const errors = [];
    const warnings = [];
    const failedRequests = [];
    const responses = [];
    const page = await context.newPage();

    page.on("console", (msg) => {
      const type = msg.type();
      const text = msg.text();
      if (type === "error") errors.push({ type: "console", message: text.slice(0, 1000) });
      if (type === "warning") warnings.push({ type: "console", message: text.slice(0, 1000) });
    });

    page.on("pageerror", (error) => {
      errors.push({ type: "pageerror", message: String(error?.message || error).slice(0, 1000) });
    });

    page.on("requestfailed", (request) => {
      failedRequests.push({
        url: request.url(),
        method: request.method(),
        failure: request.failure()?.errorText || "unknown",
      });
    });

    page.on("response", (response) => {
      const status = response.status();
      if (status >= 400) {
        responses.push({ url: response.url(), status });
      }
    });

    const startedAt = Date.now();
    let status = "OK";
    let httpStatus = null;
    let title = "";
    let screenshot = null;
    let finalUrl = null;

    try {
      const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
      httpStatus = response ? response.status() : null;
      await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      if (waitMs > 0) await page.waitForTimeout(waitMs);
      title = await page.title().catch(() => "");
      finalUrl = page.url();
      screenshot = path.join(screenshotDir, `${String(results.length + 1).padStart(2, "0")}_${slug(route.label)}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      status = classifyRouteStatus({ httpStatus, errors, failedRequests, responses });
    } catch (error) {
      status = "EXCEPTION";
      errors.push({ type: "exception", message: String(error?.message || error).slice(0, 1000) });
      try {
        screenshot = path.join(screenshotDir, `${String(results.length + 1).padStart(2, "0")}_${slug(route.label)}_exception.png`);
        await page.screenshot({ path: screenshot, fullPage: true });
      } catch {
        screenshot = null;
      }
    } finally {
      await page.close().catch(() => {});
    }

    const result = {
      route: route.path,
      label: route.label,
      url,
      final_url: finalUrl,
      status,
      http_status: httpStatus,
      title,
      screenshot,
      duration_ms: Date.now() - startedAt,
      console_error_count: errors.length,
      warning_count: warnings.length,
      failed_request_count: failedRequests.length,
      http_error_response_count: responses.length,
      errors,
      warnings: warnings.slice(0, 20),
      failed_requests: failedRequests.slice(0, 20),
      http_error_responses: responses.slice(0, 30),
    };
    results.push(result);
    console.log(`${status.padEnd(28)} ${route.path} screenshot=${screenshot || "none"}`);
  }

  await browser.close();

  const summary = {
    schema_version: "admin_smoke_screenshot_sweep.v1",
    generated_at: new Date().toISOString(),
    base_url: baseUrl,
    out_dir: outDir,
    route_count: results.length,
    ok_count: results.filter((item) => item.status === "OK").length,
    expected_auth_or_permission_count: results.filter((item) => item.status === "EXPECTED_AUTH_OR_PERMISSION").length,
    issue_count: results.filter((item) => !["OK", "EXPECTED_AUTH_OR_PERMISSION"].includes(item.status)).length,
    fail_on_error: failOnError,
    keep_runs: keepRuns,
    results,
  };

  await fs.writeFile(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));

  const markdown = [
    "# Admin Smoke Screenshot Sweep",
    "",
    `- Generated: ${summary.generated_at}`,
    `- Base URL: ${baseUrl}`,
    `- Routes: ${summary.route_count}`,
    `- OK: ${summary.ok_count}`,
    `- Expected auth/permission: ${summary.expected_auth_or_permission_count}`,
    `- Issues: ${summary.issue_count}`,
    `- Retention: latest ${keepRuns} run(s) kept`,
    "",
    "| Status | Route | HTTP | Console errors | Failed requests | Screenshot |",
    "|---|---:|---:|---:|---:|---|",
    ...results.map((item) => {
      const shot = item.screenshot ? path.relative(outDir, item.screenshot).replaceAll("\\", "/") : "";
      return `| ${item.status} | ${item.route} | ${item.http_status ?? ""} | ${item.console_error_count} | ${item.failed_request_count} | ${shot} |`;
    }),
    "",
  ].join("\n");
  await fs.writeFile(path.join(outDir, "summary.md"), markdown);

  console.log(JSON.stringify({
    schema_version: summary.schema_version,
    status: summary.issue_count ? "COMPLETED_WITH_ISSUES" : "COMPLETED_OK",
    out_dir: outDir,
    route_count: summary.route_count,
    ok_count: summary.ok_count,
    expected_auth_or_permission_count: summary.expected_auth_or_permission_count,
    issue_count: summary.issue_count,
  }, null, 2));

  if (failOnError && summary.issue_count > 0) process.exit(1);
  process.exit(0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
