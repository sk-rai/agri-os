#!/usr/bin/env node
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

function buttonLocator(page, item) {
  return item.mode === "exact"
    ? page.getByRole("button", { name: item.name, exact: true })
    : page.getByRole("button", { name: new RegExp(item.name, "i") });
}

async function main() {
  const root = argValue("--root", "test-artifacts/admin-smoke");
  const runDir = path.resolve(argValue("--run", await latestRun(root)));
  const baseUrl = (argValue("--base-url", process.env.WEB_SWEEP_BASE_URL || "http://localhost:3000") || "").replace(/\/$/, "");
  const role = argValue("--role", process.env.WEB_SWEEP_ROLE || "ENTERPRISE_ADMIN");
  const configPath = argValue("--config", "scripts/admin_smoke_role_permissions.json");
  const failOnError = process.argv.includes("--fail-on-error");

  const tenantId = argValue("--tenant-id", process.env.WEB_SWEEP_TENANT_ID || "default");
  const actorId = argValue("--actor-id", process.env.WEB_SWEEP_ACTOR_ID || "");
  const token = argValue("--token", process.env.WEB_SWEEP_TOKEN || "");

  const config = JSON.parse(await fs.readFile(configPath, "utf8"));
  const routeEntries = Object.entries(config.roles?.[role]?.routes || {});
  const outPath = path.join(runDir, "role-permissions.json");

  if (!routeEntries.length) {
    const skipped = { schema_version: "admin_smoke_role_permission_assertions.v1", status: "SKIPPED_NO_ROLE_RULES", role, run_dir: runDir, route_count: 0, ok_count: 0, failure_count: 0, results: [] };
    await fs.writeFile(outPath, JSON.stringify(skipped, null, 2));
    console.log(JSON.stringify({ schema_version: skipped.schema_version, status: skipped.status, role, route_count: 0, failure_count: 0, permissions_path: outPath }, null, 2));
    return;
  }

  const { chromium } = await import("playwright");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, ignoreHTTPSErrors: true });
  await context.addInitScript(({ tenantId, actorId, token }) => {
    if (tenantId) window.localStorage.setItem("agrios_tenant_id", tenantId);
    if (actorId) window.localStorage.setItem("agrios_user_id", actorId);
    if (token) window.localStorage.setItem("agrios_token", token);
  }, { tenantId, actorId, token });

  const results = [];

  for (const [route, expectations] of routeEntries) {
    const page = await context.newPage();
    const failures = [];
    try {
      const response = await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(800);
      const body = (await page.locator("body").innerText({ timeout: 5000 }).catch(() => "")).toLowerCase();

      for (const text of expectations.expected_text || []) {
        if (!body.includes(String(text).toLowerCase())) failures.push({ type: "missing_expected_text", text });
      }

      for (const text of expectations.forbidden_visible_text || []) {
        if (body.includes(String(text).toLowerCase())) failures.push({ type: "forbidden_visible_text", text });
      }

      for (const item of expectations.disabled_buttons || []) {
        const locator = buttonLocator(page, item);
        const count = await locator.count();
        if (count === 0) {
          if (item.presence === "required") failures.push({ type: "missing_button", name: item.name });
          continue;
        }
        for (let i = 0; i < count; i += 1) {
          const button = locator.nth(i);
          const visible = await button.isVisible().catch(() => false);
          if (visible && !(await button.isDisabled().catch(() => false))) {
            failures.push({ type: "restricted_button_enabled", name: item.name, index: i });
          }
        }
      }

      results.push({ route, status: failures.length ? "ASSERTION_FAILED" : "OK", http_status: response?.status() || null, failure_count: failures.length, failures });
    } catch (error) {
      results.push({ route, status: "EXCEPTION", failure_count: 1, failures: [{ type: "exception", message: String(error?.message || error).slice(0, 1000) }] });
    } finally {
      await page.close().catch(() => {});
    }

    const r = results.at(-1);
    console.log(`${String(r.status).padEnd(18)} ${role} ${route} failures=${r.failure_count}`);
  }

  await browser.close();

  const report = {
    schema_version: "admin_smoke_role_permission_assertions.v1",
    generated_at: new Date().toISOString(),
    run_dir: runDir,
    base_url: baseUrl,
    role,
    route_count: results.length,
    ok_count: results.filter((r) => r.status === "OK").length,
    failure_count: results.filter((r) => r.status !== "OK").length,
    results,
  };

  await fs.writeFile(outPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ schema_version: report.schema_version, status: report.failure_count ? "COMPLETED_WITH_ASSERTION_FAILURES" : "COMPLETED_OK", role, route_count: report.route_count, ok_count: report.ok_count, failure_count: report.failure_count, permissions_path: outPath }, null, 2));

  if (failOnError && report.failure_count) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
