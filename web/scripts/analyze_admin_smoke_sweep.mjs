#!/usr/bin/env node
/**
 * Analyze the latest or selected admin smoke screenshot sweep artifact.
 */

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

function argValue(name, fallback) {
  const prefix = `${name}=`;
  const found = process.argv.find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

function latestRun(root) {
  if (!fs.existsSync(root)) return null;
  const dirs = fs.readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(root, entry.name))
    .sort();
  return dirs.at(-1) || null;
}

function compact(value, limit = 220) {
  return String(value || "").replace(/\s+/g, " ").slice(0, limit);
}

function increment(map, key) {
  map.set(key, (map.get(key) || 0) + 1);
}

function printTop(title, map, limit = 20) {
  console.log("");
  console.log(title);
  console.log("=".repeat(title.length));
  if (!map.size) {
    console.log("none");
    return;
  }
  for (const [key, count] of [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit)) {
    console.log(`${count}x ${key}`);
  }
}

const root = argValue("--root", "test-artifacts/admin-smoke");
const runDir = argValue("--run", latestRun(root));

if (!runDir) {
  console.error("No smoke sweep run found.");
  process.exit(1);
}

const summaryPath = path.join(runDir, "summary.json");
if (!fs.existsSync(summaryPath)) {
  console.error(`summary.json not found: ${summaryPath}`);
  process.exit(1);
}

const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));

const statusCounts = new Map();
const consoleErrors = new Map();
const failedRequests = new Map();
const httpErrors = new Map();

for (const item of summary.results || []) {
  increment(statusCounts, item.status || "UNKNOWN");

  for (const error of item.errors || []) {
    increment(consoleErrors, `${error.type}: ${compact(error.message, 300)}`);
  }
  for (const request of item.failed_requests || []) {
    increment(failedRequests, `${request.method} ${request.url} :: ${request.failure}`);
  }
  for (const response of item.http_error_responses || []) {
    increment(httpErrors, `${response.status} ${response.url}`);
  }
}

console.log(JSON.stringify({
  schema_version: "admin_smoke_sweep_analysis.v1",
  run_dir: runDir,
  generated_at: summary.generated_at,
  base_url: summary.base_url,
  route_count: summary.route_count,
  ok_count: summary.ok_count,
  expected_auth_or_permission_count: summary.expected_auth_or_permission_count || 0,
  issue_count: summary.issue_count,
  status_counts: Object.fromEntries([...statusCounts.entries()].sort()),
}, null, 2));

printTop("Top console/page errors", consoleErrors);
printTop("Top failed requests", failedRequests);
printTop("Top HTTP error responses", httpErrors);

console.log("");
console.log("Route summary");
console.log("=============");
for (const item of summary.results || []) {
  console.log(`${String(item.status || "UNKNOWN").padEnd(28)} ${String(item.route).padEnd(28)} http=${item.http_status ?? ""} console=${item.console_error_count || 0} failed=${item.failed_request_count || 0} screenshot=${item.screenshot || ""}`);
}

process.exit(summary.issue_count ? 1 : 0);
