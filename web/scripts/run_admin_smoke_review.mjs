#!/usr/bin/env node
/**
 * One-command authenticated admin smoke review runner.
 *
 * Assumes backend and web dev servers are already running:
 * - backend: http://127.0.0.1:8000
 * - web: http://localhost:3000
 *
 * Runs:
 * 1. create local smoke session
 * 2. smoke screenshot sweep
 * 3. analyzer
 * 4. PDF report builder
 */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";

function argValue(name, fallback) {
  const prefix = `${name}=`;
  const found = process.argv.find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

function run(label, command, args, options = {}) {
  console.log("");
  console.log("=".repeat(72));
  console.log(label);
  console.log("=".repeat(72));
  const result = spawnSync(command, args, {
    stdio: options.capture ? ["ignore", "pipe", "pipe"] : "inherit",
    cwd: options.cwd || process.cwd(),
    env: options.env || process.env,
    encoding: "utf8",
  });

  if (options.capture && !options.suppressOutput) {
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
  } else if (!options.capture && !options.suppressOutput) {
    // output already inherited
  }

  if (result.status !== 0) {
    throw new Error(`${label} failed with exit code ${result.status}`);
  }
  return result;
}

async function latestRun(root) {
  const entries = await fs.readdir(root, { withFileTypes: true }).catch(() => []);
  const dirs = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(root, entry.name))
    .sort();
  return dirs.at(-1) || null;
}

async function main() {
  const repoRoot = path.resolve("..");
  const webRoot = process.cwd();
  const backendRoot = path.join(repoRoot, "backend");

  const baseUrl = argValue("--base-url", process.env.WEB_SWEEP_BASE_URL || "http://localhost:3000");
  const tenantId = argValue("--tenant-id", process.env.WEB_SWEEP_TENANT_ID || "default");
  const role = argValue("--role", process.env.WEB_SWEEP_ROLE || "ENTERPRISE_ADMIN");
  const keepRuns = argValue("--keep-runs", process.env.WEB_SWEEP_KEEP_RUNS || "1");
  const failOnError = process.argv.includes("--fail-on-error");
  const openPdf = process.argv.includes("--open");

  const session = run(
    "Create web UI smoke session",
    "../venv/bin/python",
    ["scripts/create_web_ui_smoke_session.py", "--tenant-id", tenantId, "--role", role, "--format", "json"],
    { cwd: backendRoot, capture: true, suppressOutput: true }
  );

  const sessionPayload = JSON.parse(session.stdout);
  if (sessionPayload.status !== "CREATED" || !sessionPayload.token) {
    throw new Error(`Unable to create smoke session: ${session.stdout}`);
  }

  const env = {
    ...process.env,
    WEB_SWEEP_TOKEN: sessionPayload.token,
    WEB_SWEEP_TENANT_ID: sessionPayload.tenant_id,
    WEB_SWEEP_ACTOR_ID: sessionPayload.actor_id,
    WEB_SWEEP_ROLE: sessionPayload.role,
  };

  const sweepArgs = [
    "scripts/admin_smoke_screenshot_sweep.mjs",
    `--base-url=${baseUrl}`,
    `--keep-runs=${keepRuns}`,
  ];
  if (failOnError) sweepArgs.push("--fail-on-error");

  run("Run admin smoke screenshot sweep", "node", sweepArgs, { cwd: webRoot, env });
  run("Analyze admin smoke sweep", "node", ["scripts/analyze_admin_smoke_sweep.mjs"], { cwd: webRoot, env });
  run("Assert admin smoke routes", "node", ["scripts/assert_admin_smoke_routes.mjs", `--base-url=${baseUrl}`], { cwd: webRoot, env });
  run("Assert admin smoke role permissions", "node", ["scripts/assert_admin_smoke_role_permissions.mjs", `--base-url=${baseUrl}`], { cwd: webRoot, env });
  run("Build admin smoke PDF report", "node", ["scripts/build_admin_smoke_report.mjs"], { cwd: webRoot, env });

  const runDir = await latestRun(path.join(webRoot, "test-artifacts/admin-smoke"));
  const summaryPath = path.join(runDir, "summary.json");
  const pdfPath = path.join(runDir, "admin-smoke-report.pdf");
  const summary = JSON.parse(await fs.readFile(summaryPath, "utf8"));

  let windowsPdfPath = "";
  const wslpath = spawnSync("wslpath", ["-w", pdfPath], { encoding: "utf8" });
  if (wslpath.status === 0) windowsPdfPath = wslpath.stdout.trim();

  console.log("");
  console.log("=".repeat(72));
  console.log("ADMIN SMOKE REVIEW COMPLETE");
  console.log("=".repeat(72));
  console.log(JSON.stringify({
    schema_version: "admin_smoke_review_run.v1",
    status: summary.issue_count ? "COMPLETED_WITH_ISSUES" : "COMPLETED_OK",
    base_url: baseUrl,
    tenant_id: sessionPayload.tenant_id,
    role: sessionPayload.role,
    actor_id: sessionPayload.actor_id,
    route_count: summary.route_count,
    ok_count: summary.ok_count,
    expected_auth_or_permission_count: summary.expected_auth_or_permission_count || 0,
    issue_count: summary.issue_count,
    run_dir: runDir,
    pdf_path: pdfPath,
    windows_pdf_path: windowsPdfPath,
  }, null, 2));

  if (openPdf && windowsPdfPath) {
    spawnSync("explorer.exe", [windowsPdfPath], { stdio: "ignore" });
  }

  if (summary.issue_count && failOnError) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
