#!/usr/bin/env node
/**
 * Build a single PDF review packet from an admin smoke screenshot sweep.
 *
 * Reads summary.json + screenshots and writes:
 * - report.html
 * - admin-smoke-report.pdf
 */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

function argValue(name, fallback) {
  const prefix = `${name}=`;
  const found = process.argv.find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function statusClass(status) {
  if (status === "OK") return "ok";
  if (status === "EXPECTED_AUTH_OR_PERMISSION") return "expected";
  return "issue";
}

async function latestRun(root) {
  let entries = [];
  try {
    entries = await fs.readdir(root, { withFileTypes: true });
  } catch {
    return null;
  }
  const dirs = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(root, entry.name))
    .sort();
  return dirs.at(-1) || null;
}

function screenshotSrc(runDir, screenshot) {
  if (!screenshot) return "";
  const absolute = path.isAbsolute(screenshot) ? screenshot : path.resolve(runDir, screenshot);
  return pathToFileURL(absolute).href;
}

function routePage(item, index, runDir) {
  const cls = statusClass(item.status);
  const img = screenshotSrc(runDir, item.screenshot);
  const errors = [
    ...(item.errors || []).map((e) => `${e.type}: ${e.message}`),
    ...(item.failed_requests || []).map((r) => `${r.method} ${r.url} :: ${r.failure}`),
    ...(item.http_error_responses || []).map((r) => `${r.status} ${r.url}`),
  ].slice(0, 10);

  return `
<section class="page route-page">
  <header class="route-header">
    <div>
      <div class="route-index">Screen ${index + 1} of ROUTE_COUNT</div>
      <h2>${escapeHtml(item.route)}</h2>
      <p>${escapeHtml(item.title || item.final_url || item.url || "")}</p>
    </div>
    <div class="badge ${cls}">${escapeHtml(item.status)}</div>
  </header>

  <div class="metrics">
    <span>HTTP: ${escapeHtml(item.http_status ?? "")}</span>
    <span>Console errors: ${escapeHtml(item.console_error_count || 0)}</span>
    <span>Failed requests: ${escapeHtml(item.failed_request_count || 0)}</span>
    <span>HTTP error responses: ${escapeHtml(item.http_error_response_count || 0)}</span>
    <span>Duration: ${escapeHtml(item.duration_ms || 0)} ms</span>
  </div>

  ${errors.length ? `
  <div class="errors">
    <h3>Captured issues</h3>
    <ul>${errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul>
  </div>
  ` : ""}

  <div class="screenshot-frame">
    ${img ? `<img src="${img}" alt="${escapeHtml(item.route)} screenshot" />` : `<div class="missing">No screenshot captured</div>`}
  </div>
</section>`;
}

async function main() {
  const root = argValue("--root", "test-artifacts/admin-smoke");
  const runDir = path.resolve(argValue("--run", await latestRun(root)));
  const outputName = argValue("--output", "admin-smoke-report.pdf");
  const headed = process.argv.includes("--headed");

  const summaryPath = path.join(runDir, "summary.json");
  const summary = JSON.parse(await fs.readFile(summaryPath, "utf8"));
  const pdfPath = path.join(runDir, outputName);
  const htmlPath = path.join(runDir, "report.html");

  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch (error) {
    console.error("Playwright is required. Run: cd web && npm install -D playwright && npx playwright install chromium");
    console.error(error);
    process.exit(2);
  }

  const routeRows = (summary.results || []).map((item, index) => `
    <tr>
      <td>${index + 1}</td>
      <td>${escapeHtml(item.route)}</td>
      <td><span class="mini-badge ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
      <td>${escapeHtml(item.http_status ?? "")}</td>
      <td>${escapeHtml(item.console_error_count || 0)}</td>
      <td>${escapeHtml(item.failed_request_count || 0)}</td>
    </tr>
  `).join("");

  const pages = (summary.results || [])
    .map((item, index) => routePage(item, index, runDir))
    .join("")
    .replaceAll("ROUTE_COUNT", String(summary.route_count || (summary.results || []).length));

  const html = `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Admin Smoke Screenshot Report</title>
<style>
  @page { size: A4 landscape; margin: 12mm; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: Arial, Helvetica, sans-serif;
    color: #172033;
    background: #f5f7fb;
  }
  .page {
    page-break-after: always;
    min-height: 184mm;
    background: white;
    padding: 18px 22px;
    border-radius: 12px;
  }
  .cover h1 {
    margin: 0 0 8px;
    font-size: 30px;
  }
  .cover .subtitle {
    color: #556070;
    margin-bottom: 20px;
  }
  .summary-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin: 20px 0;
  }
  .card {
    border: 1px solid #dbe3ef;
    border-radius: 10px;
    padding: 12px;
    background: #f8fafc;
  }
  .card .label { color: #64748b; font-size: 12px; }
  .card .value { font-size: 24px; font-weight: 700; margin-top: 4px; }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
  }
  th, td {
    padding: 6px 8px;
    border-bottom: 1px solid #e5eaf2;
    text-align: left;
  }
  th {
    background: #f1f5f9;
    color: #334155;
  }
  .route-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 10px;
  }
  .route-header h2 {
    margin: 2px 0 3px;
    font-size: 22px;
  }
  .route-header p {
    margin: 0;
    color: #64748b;
    font-size: 11px;
  }
  .route-index {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
    font-size: 10px;
    font-weight: 700;
  }
  .badge, .mini-badge {
    border-radius: 999px;
    padding: 6px 10px;
    font-weight: 700;
    font-size: 11px;
    white-space: nowrap;
  }
  .mini-badge { padding: 3px 7px; font-size: 9px; }
  .ok { background: #dcfce7; color: #166534; }
  .expected { background: #fef3c7; color: #92400e; }
  .issue { background: #fee2e2; color: #991b1b; }
  .metrics {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0 12px;
    font-size: 10px;
  }
  .metrics span {
    background: #eef2ff;
    color: #3730a3;
    border-radius: 999px;
    padding: 4px 8px;
  }
  .errors {
    border: 1px solid #fecaca;
    background: #fff1f2;
    border-radius: 8px;
    padding: 8px 10px;
    margin-bottom: 10px;
    font-size: 10px;
  }
  .errors h3 { margin: 0 0 4px; font-size: 11px; }
  .errors ul { margin: 0; padding-left: 16px; }
  .screenshot-frame {
    border: 1px solid #dbe3ef;
    background: #f8fafc;
    border-radius: 10px;
    padding: 8px;
    height: 137mm;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    overflow: hidden;
  }
  .screenshot-frame img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border: 1px solid #e2e8f0;
    background: white;
  }
  .missing {
    color: #64748b;
    padding: 40px;
  }
  .footer-note {
    margin-top: 16px;
    color: #64748b;
    font-size: 11px;
  }
</style>
</head>
<body>
<section class="page cover">
  <h1>Admin Smoke Screenshot Report</h1>
  <div class="subtitle">Generated from Playwright route sweep artifacts.</div>

  <div class="summary-grid">
    <div class="card"><div class="label">Routes</div><div class="value">${escapeHtml(summary.route_count)}</div></div>
    <div class="card"><div class="label">OK</div><div class="value">${escapeHtml(summary.ok_count)}</div></div>
    <div class="card"><div class="label">Expected auth</div><div class="value">${escapeHtml(summary.expected_auth_or_permission_count || 0)}</div></div>
    <div class="card"><div class="label">Issues</div><div class="value">${escapeHtml(summary.issue_count)}</div></div>
    <div class="card"><div class="label">Base URL</div><div class="value" style="font-size:13px">${escapeHtml(summary.base_url)}</div></div>
  </div>

  <p><strong>Generated:</strong> ${escapeHtml(summary.generated_at)}</p>
  <p><strong>Artifact directory:</strong> ${escapeHtml(runDir)}</p>

  <table>
    <thead>
      <tr><th>#</th><th>Route</th><th>Status</th><th>HTTP</th><th>Console</th><th>Failed requests</th></tr>
    </thead>
    <tbody>${routeRows}</tbody>
  </table>

  <div class="footer-note">
    This PDF is for human review. Generated screenshots are gitignored and retained according to the smoke sweep retention setting.
  </div>
</section>
${pages}
</body>
</html>`;

  await fs.writeFile(htmlPath, html, "utf8");

  const browser = await chromium.launch({ headless: !headed });
  try {
    const page = await browser.newPage();
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
    await page.pdf({
      path: pdfPath,
      format: "A4",
      landscape: true,
      printBackground: true,
      preferCSSPageSize: true,
    });
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify({
    schema_version: "admin_smoke_pdf_report.v1",
    status: "CREATED",
    run_dir: runDir,
    html_path: htmlPath,
    pdf_path: pdfPath,
    route_count: summary.route_count,
    issue_count: summary.issue_count,
  }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
