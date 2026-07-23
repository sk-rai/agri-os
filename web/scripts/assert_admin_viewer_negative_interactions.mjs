#!/usr/bin/env node
/**
 * Non-mutating negative interaction checks for ADMIN_VIEWER.
 *
 * These checks click read-only/disabled controls where safe and verify that
 * restricted mutation UI does not become actionable.
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
  return entries.filter((e) => e.isDirectory()).map((e) => path.join(root, e.name)).sort().at(-1) || null;
}

async function authedContext(chromium, { tenantId, actorId, token }) {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, ignoreHTTPSErrors: true });
  await context.addInitScript(({ tenantId, actorId, token }) => {
    if (tenantId) window.localStorage.setItem("agrios_tenant_id", tenantId);
    if (actorId) window.localStorage.setItem("agrios_user_id", actorId);
    if (token) window.localStorage.setItem("agrios_token", token);
  }, { tenantId, actorId, token });
  return { browser, context };
}

async function main() {
  const role = argValue("--role", process.env.WEB_SWEEP_ROLE || "ADMIN_VIEWER");
  const baseUrl = (argValue("--base-url", process.env.WEB_SWEEP_BASE_URL || "http://localhost:3000") || "").replace(/\/$/, "");
  const root = argValue("--root", "test-artifacts/admin-smoke");
  const runDir = path.resolve(argValue("--run", await latestRun(root)));
  const failOnError = process.argv.includes("--fail-on-error");

  const tenantId = argValue("--tenant-id", process.env.WEB_SWEEP_TENANT_ID || "default");
  const actorId = argValue("--actor-id", process.env.WEB_SWEEP_ACTOR_ID || "");
  const token = argValue("--token", process.env.WEB_SWEEP_TOKEN || "");

  const results = [];

  if (role !== "ADMIN_VIEWER") {
    const skipped = {
      schema_version: "admin_viewer_negative_interactions.v1",
      status: "SKIPPED_UNSUPPORTED_ROLE",
      role,
      run_dir: runDir,
      check_count: 0,
      failure_count: 0,
      results,
    };
    const outPath = path.join(runDir, "negative-interactions.json");
    await fs.writeFile(outPath, JSON.stringify(skipped, null, 2));
    console.log(JSON.stringify({ schema_version: skipped.schema_version, status: skipped.status, role, check_count: 0, failure_count: 0, negative_interactions_path: outPath }, null, 2));
    return;
  }

  const { chromium } = await import("playwright");
  const { browser, context } = await authedContext(chromium, { tenantId, actorId, token });

  async function checkTenants() {
    const page = await context.newPage();
    const failures = [];
    try {
      await page.goto(`${baseUrl}/tenants`, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      const button = page.getByRole("button", { name: "+ New Tenant", exact: true });
      if ((await button.count()) !== 1) {
        failures.push({ type: "missing_button", name: "+ New Tenant" });
      } else if (!(await button.isDisabled())) {
        failures.push({ type: "restricted_button_enabled", name: "+ New Tenant" });
      } else {
        await button.click({ force: true }).catch(() => {});
        await page.waitForTimeout(500);
        const body = await page.locator("body").innerText();
        if (body.includes("Register New Tenant")) {
          failures.push({ type: "restricted_form_opened", text: "Register New Tenant" });
        }
      }
    } finally {
      await page.close().catch(() => {});
    }
    results.push({ check: "admin_viewer_cannot_open_tenant_create_form", route: "/tenants", status: failures.length ? "FAILED" : "OK", failures });
  }

  async function checkWorkflows() {
    const page = await context.newPage();
    const failures = [];
    try {
      await page.goto(`${baseUrl}/workflows`, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(800);

      for (const name of ["Restore as draft", "Dry run", "Backfill eligible pins"]) {
        const locator = page.getByRole("button", { name, exact: true });
        const count = await locator.count();
        for (let i = 0; i < count; i += 1) {
          const button = locator.nth(i);
          if ((await button.isVisible().catch(() => false)) && !(await button.isDisabled().catch(() => false))) {
            failures.push({ type: "restricted_button_enabled", name, index: i });
          }
        }
      }
    } finally {
      await page.close().catch(() => {});
    }
    results.push({ check: "admin_viewer_workflow_mutation_controls_disabled", route: "/workflows", status: failures.length ? "FAILED" : "OK", failures });
  }

  await checkTenants();
  await checkWorkflows();
  await browser.close();

  const report = {
    schema_version: "admin_viewer_negative_interactions.v1",
    generated_at: new Date().toISOString(),
    role,
    run_dir: runDir,
    base_url: baseUrl,
    check_count: results.length,
    ok_count: results.filter((r) => r.status === "OK").length,
    failure_count: results.filter((r) => r.status !== "OK").length,
    results,
  };

  const outPath = path.join(runDir, "negative-interactions.json");
  await fs.writeFile(outPath, JSON.stringify(report, null, 2));

  for (const item of results) {
    console.log(`${String(item.status).padEnd(8)} ${item.check} failures=${item.failures.length}`);
  }

  console.log(JSON.stringify({
    schema_version: report.schema_version,
    status: report.failure_count ? "COMPLETED_WITH_FAILURES" : "COMPLETED_OK",
    role,
    check_count: report.check_count,
    ok_count: report.ok_count,
    failure_count: report.failure_count,
    negative_interactions_path: outPath,
  }, null, 2));

  if (failOnError && report.failure_count) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
