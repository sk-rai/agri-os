#!/usr/bin/env node
/**
 * Read-only inventory of visible buttons across a smoke run.
 *
 * Useful before adding negative/positive interaction tests: it records button
 * text, disabled state, visibility, and route without clicking anything.
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

async function main() {
  const root = argValue("--root", "test-artifacts/admin-smoke");
  const runDir = path.resolve(argValue("--run", await latestRun(root)));
  const baseUrl = (argValue("--base-url", process.env.WEB_SWEEP_BASE_URL || "http://localhost:3000") || "").replace(/\/$/, "");
  const role = argValue("--role", process.env.WEB_SWEEP_ROLE || "ADMIN_VIEWER");
  const tenantId = argValue("--tenant-id", process.env.WEB_SWEEP_TENANT_ID || "default");
  const actorId = argValue("--actor-id", process.env.WEB_SWEEP_ACTOR_ID || "");
  const token = argValue("--token", process.env.WEB_SWEEP_TOKEN || "");

  const summary = JSON.parse(await fs.readFile(path.join(runDir, "summary.json"), "utf8"));
  const { chromium } = await import("playwright");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, ignoreHTTPSErrors: true });

  await context.addInitScript(({ tenantId, actorId, token }) => {
    if (tenantId) window.localStorage.setItem("agrios_tenant_id", tenantId);
    if (actorId) window.localStorage.setItem("agrios_user_id", actorId);
    if (token) window.localStorage.setItem("agrios_token", token);
  }, { tenantId, actorId, token });

  const routeResults = [];
  const flat = [];

  for (const routeResult of summary.results || []) {
    const route = routeResult.route;
    const page = await context.newPage();
    const buttons = [];

    try {
      const response = await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(700);

      const count = await page.locator("button").count();
      for (let i = 0; i < count; i += 1) {
        const button = page.locator("button").nth(i);
        const visible = await button.isVisible().catch(() => false);
        const text = (await button.innerText().catch(() => "")).trim().replace(/\s+/g, " ");
        const disabled = await button.isDisabled().catch(() => false);
        const title = await button.getAttribute("title").catch(() => null);

        if (!visible && !text) continue;

        const item = { route, index: i, text, disabled, visible, title };
        buttons.push(item);
        flat.push(item);
      }

      routeResults.push({ route, http_status: response?.status() || null, button_count: buttons.length, buttons });
    } catch (error) {
      routeResults.push({ route, status: "EXCEPTION", button_count: 0, error: String(error?.message || error).slice(0, 1000), buttons: [] });
    } finally {
      await page.close().catch(() => {});
    }

    console.log(`${route.padEnd(28)} buttons=${buttons.length}`);
  }

  await browser.close();

  const actionWords = /create|new|edit|delete|save|approve|reject|import|upload|publish|enable|disable|restore|backfill|assign|revoke|apply/i;
  const actionable = flat.filter((item) => actionWords.test(item.text || item.title || ""));

  const report = {
    schema_version: "admin_smoke_button_inventory.v1",
    generated_at: new Date().toISOString(),
    run_dir: runDir,
    base_url: baseUrl,
    role,
    route_count: routeResults.length,
    button_count: flat.length,
    actionable_button_count: actionable.length,
    actionable_enabled_count: actionable.filter((item) => item.visible && !item.disabled).length,
    routes: routeResults,
    actionable_buttons: actionable,
  };

  const outPath = path.join(runDir, "button-inventory.json");
  await fs.writeFile(outPath, JSON.stringify(report, null, 2));

  console.log(JSON.stringify({
    schema_version: report.schema_version,
    role,
    route_count: report.route_count,
    button_count: report.button_count,
    actionable_button_count: report.actionable_button_count,
    actionable_enabled_count: report.actionable_enabled_count,
    inventory_path: outPath,
  }, null, 2));

  for (const item of actionable.slice(0, 80)) {
    console.log(`${item.disabled ? "DISABLED" : "ENABLED "} ${item.route} :: ${item.text || item.title}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
