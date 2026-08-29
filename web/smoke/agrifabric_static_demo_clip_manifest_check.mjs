import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const manifestPath = "docs/agrifabric-static-demo-clip-manifest.json";
const manifest = JSON.parse(fs.readFileSync(path.join(root, manifestPath), "utf8"));

let failed = false;

function check(name, condition, evidence = undefined) {
  if (condition) {
    console.log("PASS " + name);
  } else {
    failed = true;
    console.error("FAIL " + name);
  }
  if (evidence !== undefined) console.log(JSON.stringify(evidence, null, 2));
}

console.log("========================================================================");
console.log("AGRIFABRIC STATIC DEMO CLIP MANIFEST CHECK");
console.log("========================================================================");

check("Schema version is current", manifest.schema_version === "agrifabric_static_demo_clip_manifest.v1");
check("Rendering is deferred", manifest.status === "planned_no_render");
check("Timing doc is linked", manifest.source_timing_doc === "docs/agrifabric-static-demo-voiceover-timing.md");
check("Four static clips are planned", Array.isArray(manifest.clips) && manifest.clips.length === 4);

const expectedIds = [
  "agrifabric-v02-product-pillars-static",
  "agrifabric-v10-relationship-graph-static",
  "agrifabric-v08-geography-digipin-static",
  "agrifabric-v11-insurance-roadmap-static"
];

for (const id of expectedIds) {
  const clip = manifest.clips.find((item) => item.id === id);
  check("Clip exists: " + id, Boolean(clip));
  if (!clip) continue;

  check("Thumbnail exists for " + id, fs.existsSync(path.join(root, clip.thumbnail)), { thumbnail: clip.thumbnail });
  check("Primary source is screenshot path for " + id, clip.primary_asset.includes("web/smoke/screenshots/agrifabric/"), { primary_asset: clip.primary_asset });
  check("Output is planned mp4 for " + id, clip.planned_output.endsWith(".mp4"), { planned_output: clip.planned_output });
  check("Claim boundary present for " + id, clip.claim_boundary.length > 40);
}

check("No DB writes guardrail", manifest.guardrails?.no_database_writes === true);
check("No Android capture guardrail", manifest.guardrails?.no_android_capture_required === true);
check("No automated decisioning guardrail", manifest.guardrails?.no_automated_claim_decisioning_claims === true);

console.log("========================================================================");
console.log(failed ? "AGRIFABRIC STATIC DEMO CLIP MANIFEST CHECK FAILED" : "AGRIFABRIC STATIC DEMO CLIP MANIFEST CHECK PASSED");
console.log("========================================================================");

process.exit(failed ? 1 : 0);
