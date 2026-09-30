#!/usr/bin/env node
/**
 * Reuse the authenticated gated-readiness Playwright smoke across
 * geographically diverse state fixtures.
 */

import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

function argValue(name, fallback) {
  const prefix = `${name}=`;
  const found = process.argv.find((arg) =>
    arg.startsWith(prefix),
  );
  return found ? found.slice(prefix.length) : fallback;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || process.cwd(),
    env: options.env || process.env,
    encoding: "utf8",
    stdio: options.capture
      ? ["ignore", "pipe", "pipe"]
      : "inherit",
  });

  if (result.status !== 0) {
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
    throw new Error(
      `${command} failed with exit code ${result.status}`,
    );
  }

  return result;
}

const scriptPath = fileURLToPath(import.meta.url);
const scriptRoot = path.dirname(scriptPath);
const webRoot = path.resolve(scriptRoot, "..");
const repoRoot = path.resolve(webRoot, "..");
const backendRoot = path.join(repoRoot, "backend");

const tenantId = argValue(
  "--tenant-id",
  process.env.WEB_SWEEP_TENANT_ID || "default",
);
const role = argValue(
  "--role",
  process.env.WEB_SWEEP_ROLE || "ENTERPRISE_ADMIN",
);
const webBaseUrl = argValue(
  "--web-base-url",
  process.env.WEB_BASE_URL || "http://localhost:3000",
);
const maxReadMs = argValue(
  "--max-read-ms",
  process.env.READINESS_SWEEP_MAX_MS || "5000",
);

const states = [
  "Andaman And Nicobar Islands",
  "Assam",
  "Karnataka",
  "Rajasthan",
  "Kerala",
];

const session = run(
  "../venv/bin/python",
  [
    "scripts/create_web_ui_smoke_session.py",
    "--tenant-id",
    tenantId,
    "--role",
    role,
    "--format",
    "json",
  ],
  {
    cwd: backendRoot,
    capture: true,
  },
);

const payload = JSON.parse(session.stdout);
if (payload.status !== "CREATED" || !payload.token) {
  throw new Error(
    "Unable to create an authenticated smoke session.",
  );
}

console.log(JSON.stringify({
  schema_version:
    "geography_layer_readiness_diverse_sweep_runner.v1",
  status: "SESSION_CREATED",
  tenant_id: payload.tenant_id,
  actor_id: payload.actor_id,
  role: payload.role,
  expires_in_seconds: payload.expires_in_seconds,
  token_logged: false,
  maximum_allowed_read_ms: Number(maxReadMs),
}, null, 2));

for (const state of states) {
  console.log(`=== SWEEP STATE: ${state} ===`);

  run(
    "node",
    ["smoke/geography_layer_readiness_gated_smoke.mjs"],
    {
      cwd: webRoot,
      env: {
        ...process.env,
        WEB_SWEEP_TOKEN: payload.token,
        WEB_SWEEP_TENANT_ID: payload.tenant_id,
        WEB_SWEEP_ACTOR_ID: payload.actor_id,
        WEB_SWEEP_ROLE: payload.role,
        WEB_BASE_URL: webBaseUrl,
        READINESS_SWEEP_STATE: state,
        READINESS_SWEEP_MAX_MS: maxReadMs,
      },
    },
  );
}

console.log(JSON.stringify({
  schema_version:
    "geography_layer_readiness_diverse_sweep.v1",
  status: "PASSED",
  state_count: states.length,
  states,
  maximum_allowed_read_ms: Number(maxReadMs),
  read_only: true,
}, null, 2));
