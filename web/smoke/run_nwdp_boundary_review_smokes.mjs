import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));

const smokes = [
  "nwdp_boundary_review_smoke.mjs",
  "nwdp_boundary_review_save_smoke.mjs",
];

for (const smoke of smokes) {
  console.log("\n========================================================================");
  console.log(`RUNNING ${smoke}`);
  console.log("========================================================================");

  const result = spawnSync(process.execPath, [path.join(scriptDir, smoke)], {
    stdio: "inherit",
    env: process.env,
  });

  if (result.status !== 0) {
    console.error(`\nFAILED ${smoke}`);
    process.exit(result.status || 1);
  }
}

console.log("\n========================================================================");
console.log("NWDP BOUNDARY REVIEW WEB SMOKES PASSED");
console.log("========================================================================");
