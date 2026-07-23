#!/usr/bin/env node
/**
 * Read-only page-level assertions for the latest admin smoke sweep.
 *
 * Re-visits each route with authenticated localStorage, checks expected visible
 * text and forbidden error text, and continues after failures.
 */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

function argValue(name, fallback) {
  const prefix = `${name}=`;
  const found = process.argv.find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

async function latestRun(root) {
  const entries = await fs.readdir(root, { withFileTypes: true }).catch(() => []);
  const dirs = entries.filter((entry) => entry.isDirectory()).map((entry) => path.join(root, entry.name)).sort();
  return dirs.at(-1) || null;
}

async function main() {
  const root = argValue("--root", "test-artifacts/admin-smoke");
  const runDir = path.resolve(argValue("--run", await latestRun(root)));
  const baseUrl = (argValue("--base-url", process.env.WEB_SWEEP_BASE_URL || "http://localhost:3000") || "").replace(/\/$/, "");
  const configPath = argValue("--config", "scripts/admin_smoke_assertions.json");
  const failOnError = process.argv.includes("--fail-on-error");

  const tenantId = argValue("--tenant-id", process.env.WEB_SWEEP_TENANT_ID || "default");
  const actorId = argValue("--actor-id", process.env.WEB_SWEEP_ACTOR_ID || "");
  const token = argValue("--token", process.env.WEB_SWEEP_TOKEN || "");

  const summary = JSON.parse(await fs.readFile(path.join(runDir, "summary.json"), "utf8"));
  const config = JSON.parse(await fs.readFile(configPath, "utf8"));

  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch (error) {
    console.error("Playwright is required. Run: cd web && npm install -D playwright && npx playwright install chromium");
    console.error(error);
    process.exit(2);
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, ignoreHTTPSErrors: true });
  await context.addInitScript(({ tenantId, actorId, token }) => {
    if (tenantId) window.localStorage.setItem("agrios_tenant_id", tenantId);
    if (actorId) window.localStorage.setItem("agrios_user_id", actorId);
    if (token) window.localStorage.setItem("agrios_token", token);
  }, { tenantId, actorId, token });

  const defaultForbidden = config.defaults?.forbidden_visible_text || [];
  const results = [];

  for (const routeResult of summary.results || []) {
    const route = routeResult.route;
    const expectations = config.routes?.[route] || {};
    const expectedText = expectations.expected_text || [];
    const forbiddenText = [...defaultForbidden, ...(expectations.forbidden_visible_text || [])];
    const url = `${baseUrl}${route}`;
    const page = await context.newPage();
    const failures = [];
    const passed = [];

    try {
      const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(800);

      const bodyText = await page.locator("body").innerText({ timeout: 5000 }).catch(() => "");

      for (const text of expectedText) {
        if (bodyText.toLowerCase().includes(String(text).toLowerCase())) {
          passed.push({ type: "expected_text", text });
        } else {
          failures.push({ type: "missing_expected_text", text });
        }
      }

      for (const text of forbiddenText) {
        if (bodyText.toLowerCase().includes(String(text).toLowerCase())) {
          failures.push({ type: "forbidden_visible_text", text });
        }
      }

      results.push({
        route,
        status: failures.length ? "ASSERTION_FAILED" : "OK",
        http_status: response ? response.status() : null,
        expected_text_count: expectedText.length,
        passed_count: passed.length,
        failure_count: failures.length,
        failures,
      });
    } catch (error) {
      results.push({
        route,
        status: "EXCEPTION",
        failure_count: 1,
        failures: [{ type: "exception", message: String(error?.message || error).slice(0, 1000) }],
      });
    } finally {
      await page.close().catch(() => {});
    }

    const latest = results.at(-1);
    console.log(`${String(latest.status).padEnd(18)} ${route} failures=${latest.failure_count}`);
  }

  await browser.close();

  const report = {
    schema_version: "admin_smoke_route_assertions.v1",
    generated_at: new Date().toISOString(),
    run_dir: runDir,
    base_url: baseUrl,
    route_count: results.length,
    ok_count: results.filter((item) => item.status === "OK").length,
    failure_count: results.filter((item) => item.status !== "OK").length,
    results,
  };

  const outPath = path.join(runDir, "assertions.json");
  await fs.writeFile(outPath, JSON.stringify(report, null, 2));

  console.log(JSON.stringify({
    schema_version: report.schema_version,
    status: report.failure_count ? "COMPLETED_WITH_ASSERTION_FAILURES" : "COMPLETED_OK",
    run_dir: runDir,
    route_count: report.route_count,
    ok_count: report.ok_count,
    failure_count: report.failure_count,
    assertions_path: outPath,
  }, null, 2));

  if (failOnError && report.failure_count) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
