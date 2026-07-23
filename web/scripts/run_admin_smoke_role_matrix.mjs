#!/usr/bin/env node
/**
 * Run the authenticated admin smoke review for multiple roles and summarize.
 *
 * Assumes backend and web dev servers are already running. Each role gets its
 * own screenshot/PDF artifact run under test-artifacts/admin-smoke/.
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

function hasFlag(name) {
  return process.argv.includes(name);
}

async function latestRun(root) {
  const entries = await fs.readdir(root, { withFileTypes: true }).catch(() => []);
  return entries.filter((e) => e.isDirectory()).map((e) => path.join(root, e.name)).sort().at(-1) || null;
}

function runReview({ baseUrl, tenantId, role, keepRuns, failOnError }) {
  const args = [
    "scripts/run_admin_smoke_review.mjs",
    `--base-url=${baseUrl}`,
    `--tenant-id=${tenantId}`,
    `--role=${role}`,
    `--keep-runs=${keepRuns}`,
  ];
  if (failOnError) args.push("--fail-on-error");

  const result = spawnSync("node", args, {
    cwd: process.cwd(),
    stdio: "inherit",
    env: process.env,
    encoding: "utf8",
  });

  return result.status ?? 1;
}

async function main() {
  const baseUrl = argValue("--base-url", process.env.WEB_SWEEP_BASE_URL || "http://localhost:3000");
  const tenantId = argValue("--tenant-id", process.env.WEB_SWEEP_TENANT_ID || "default");
  const keepRuns = argValue("--keep-runs", process.env.WEB_SWEEP_KEEP_RUNS || "2");
  const roles = argValue("--roles", process.env.WEB_SWEEP_ROLES || "ENTERPRISE_ADMIN,ADMIN_VIEWER")
    .split(",")
    .map((role) => role.trim())
    .filter(Boolean);
  const failOnError = hasFlag("--fail-on-error");
  const root = path.resolve("test-artifacts/admin-smoke");
  const matrixDir = path.resolve("test-artifacts/admin-smoke-matrix");
  await fs.mkdir(matrixDir, { recursive: true });

  const results = [];

  for (const role of roles) {
    console.log("");
    console.log("#".repeat(80));
    console.log(`ADMIN SMOKE ROLE MATRIX: ${role}`);
    console.log("#".repeat(80));

    const exit_code = runReview({ baseUrl, tenantId, role, keepRuns, failOnError });
    const runDir = await latestRun(root);
    const summaryPath = runDir ? path.join(runDir, "summary.json") : null;
    const rolePermissionsPath = runDir ? path.join(runDir, "role-permissions.json") : null;
    const pdfPath = runDir ? path.join(runDir, "admin-smoke-report.pdf") : null;

    let summary = null;
    let rolePermissions = null;

    if (summaryPath) {
      summary = JSON.parse(await fs.readFile(summaryPath, "utf8"));
    }
    if (rolePermissionsPath) {
      rolePermissions = JSON.parse(await fs.readFile(rolePermissionsPath, "utf8").catch(() => "{}"));
    }

    let windowsPdfPath = "";
    if (pdfPath) {
      const wslpath = spawnSync("wslpath", ["-w", pdfPath], { encoding: "utf8" });
      if (wslpath.status === 0) windowsPdfPath = wslpath.stdout.trim();
    }

    results.push({
      role,
      exit_code,
      status: exit_code === 0 && summary?.issue_count === 0 && (rolePermissions?.failure_count || 0) === 0 ? "OK" : "ISSUES",
      run_dir: runDir,
      route_count: summary?.route_count ?? 0,
      ok_count: summary?.ok_count ?? 0,
      smoke_issue_count: summary?.issue_count ?? null,
      role_permission_route_count: rolePermissions?.route_count ?? 0,
      role_permission_failure_count: rolePermissions?.failure_count ?? 0,
      pdf_path: pdfPath,
      windows_pdf_path: windowsPdfPath,
    });
  }

  const report = {
    schema_version: "admin_smoke_role_matrix.v1",
    generated_at: new Date().toISOString(),
    base_url: baseUrl,
    tenant_id: tenantId,
    role_count: results.length,
    ok_count: results.filter((item) => item.status === "OK").length,
    issue_count: results.filter((item) => item.status !== "OK").length,
    results,
  };

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const jsonPath = path.join(matrixDir, `${stamp}.json`);
  const mdPath = path.join(matrixDir, `${stamp}.md`);

  const lines = [
    "# Admin Smoke Role Matrix",
    "",
    `- Generated: ${report.generated_at}`,
    `- Base URL: ${report.base_url}`,
    `- Tenant: ${report.tenant_id}`,
    `- Roles: ${report.role_count}`,
    `- OK: ${report.ok_count}`,
    `- Issues: ${report.issue_count}`,
    "",
    "| Role | Status | Routes OK | Smoke issues | Permission assertion failures | PDF |",
    "|---|---:|---:|---:|---:|---|",
    ...results.map((item) => `| ${item.role} | ${item.status} | ${item.ok_count}/${item.route_count} | ${item.smoke_issue_count ?? "?"} | ${item.role_permission_failure_count} | ${item.windows_pdf_path || item.pdf_path || ""} |`),
    "",
  ];

  await fs.writeFile(jsonPath, JSON.stringify(report, null, 2));
  await fs.writeFile(mdPath, lines.join("\n"));

  console.log("");
  console.log("=".repeat(72));
  console.log("ADMIN SMOKE ROLE MATRIX COMPLETE");
  console.log("=".repeat(72));
  console.log(JSON.stringify({
    schema_version: report.schema_version,
    status: report.issue_count ? "COMPLETED_WITH_ISSUES" : "COMPLETED_OK",
    role_count: report.role_count,
    ok_count: report.ok_count,
    issue_count: report.issue_count,
    json_path: jsonPath,
    markdown_path: mdPath,
  }, null, 2));

  if (failOnError && report.issue_count) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
