#!/usr/bin/env node
/**
 * Guardrail for enabled ADMIN_VIEWER action-looking buttons.
 *
 * Reads button-inventory.json from the latest smoke run and fails if an enabled
 * action-looking button is not explicitly allowlisted.
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

function keyOf(item) {
  return `${item.route}::${String(item.text || "").trim()}`;
}

async function main() {
  const root = argValue("--root", "test-artifacts/admin-smoke");
  const runDir = path.resolve(argValue("--run", await latestRun(root)));
  const configPath = argValue("--config", "scripts/admin_viewer_enabled_action_allowlist.json");
  const failOnError = process.argv.includes("--fail-on-error");

  const inventoryPath = path.join(runDir, "button-inventory.json");
  const inventory = JSON.parse(await fs.readFile(inventoryPath, "utf8"));
  const config = JSON.parse(await fs.readFile(configPath, "utf8"));

  const allowed = new Set((config.allowed_enabled_action_buttons || []).map(keyOf));
  const enabledActionButtons = (inventory.actionable_buttons || []).filter((item) => item.visible && !item.disabled);
  const unexpected = enabledActionButtons.filter((item) => !allowed.has(keyOf(item)));
  const unusedAllowlist = [...allowed].filter((key) => !enabledActionButtons.some((item) => keyOf(item) === key));

  const report = {
    schema_version: "admin_viewer_enabled_action_guardrail.v1",
    generated_at: new Date().toISOString(),
    run_dir: runDir,
    role: inventory.role,
    enabled_action_count: enabledActionButtons.length,
    allowed_count: enabledActionButtons.length - unexpected.length,
    unexpected_count: unexpected.length,
    unused_allowlist_count: unusedAllowlist.length,
    unexpected_enabled_actions: unexpected,
    unused_allowlist: unusedAllowlist,
  };

  const outPath = path.join(runDir, "enabled-action-guardrail.json");
  await fs.writeFile(outPath, JSON.stringify(report, null, 2));

  for (const item of enabledActionButtons) {
    const status = allowed.has(keyOf(item)) ? "ALLOWED" : "UNEXPECTED";
    console.log(`${status.padEnd(10)} ${item.route} :: ${item.text}`);
  }

  if (unusedAllowlist.length) {
    console.log("Unused allowlist entries:");
    for (const item of unusedAllowlist) console.log(`- ${item}`);
  }

  console.log(JSON.stringify({
    schema_version: report.schema_version,
    status: report.unexpected_count ? "COMPLETED_WITH_UNEXPECTED_ACTIONS" : "COMPLETED_OK",
    role: report.role,
    enabled_action_count: report.enabled_action_count,
    unexpected_count: report.unexpected_count,
    unused_allowlist_count: report.unused_allowlist_count,
    guardrail_path: outPath,
  }, null, 2));

  if (failOnError && report.unexpected_count) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
