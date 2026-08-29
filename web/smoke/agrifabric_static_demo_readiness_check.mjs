import fs from "node:fs";
import path from "node:path";

const root = process.cwd();

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function exists(relativePath) {
  return fs.existsSync(path.join(root, relativePath));
}

function pass(name, evidence = null) {
  console.log(`PASS ${name}`);
  if (evidence !== null) {
    console.log(JSON.stringify(evidence, null, 2));
  }
}

function fail(name, evidence = null) {
  console.error(`FAIL ${name}`);
  if (evidence !== null) {
    console.error(JSON.stringify(evidence, null, 2));
  }
  process.exitCode = 1;
}

function check(name, condition, evidence = null) {
  if (condition) pass(name, evidence);
  else fail(name, evidence);
}

const pagePath = "web/src/app/agrifabric/AgriFabricLandingClient.tsx";
const manifestPath = "docs/agrifabric-demo-video-production-manifest.md";
const timingPath = "docs/agrifabric-static-demo-voiceover-timing.md";
const backlogPath = "docs/landing-page-implementation-backlog.md";
const docsReadmePath = "docs/README.md";

const thumbnails = [
  "web/public/demo-assets/agrifabric-v02-product-pillars-thumb.png",
  "web/public/demo-assets/agrifabric-v10-relationship-graph-thumb.png",
  "web/public/demo-assets/agrifabric-v08-geography-digipin-thumb.png",
  "web/public/demo-assets/agrifabric-v11-insurance-roadmap-thumb.png",
];

const page = read(pagePath);
const manifest = read(manifestPath);
const timing = read(timingPath);
const backlog = read(backlogPath);
const docsReadme = read(docsReadmePath);

console.log("========================================================================");
console.log("AGRIFABRIC STATIC DEMO READINESS CHECK");
console.log("========================================================================");

check("AgriFabric landing client exists", exists(pagePath), { path: pagePath });
check("Production manifest exists", exists(manifestPath), { path: manifestPath });
check("Voiceover timing doc exists", exists(timingPath), { path: timingPath });

for (const thumbnail of thumbnails) {
  const stat = exists(thumbnail) ? fs.statSync(path.join(root, thumbnail)) : null;
  check(`Thumbnail exists: ${path.basename(thumbnail)}`, Boolean(stat && stat.size > 0), {
    path: thumbnail,
    bytes: stat?.size ?? 0,
  });
}

check("Operations demo strip includes V02 product card", page.includes("Six pillars of AgriFabric"));
check("Operations demo strip includes V10 graph card", page.includes("Relationship graph"));
check("Operations demo strip includes V08 geography card", page.includes("Geography + DigiPin"));
check("Operations demo strip includes V11 roadmap card", page.includes("Insurance integrity roadmap"));
check("Android-heavy clips remain marked later", page.includes("Android later") && page.includes("Hold until NWDP overlay completes."));
check("Roadmap card is explicitly bounded", page.includes("explicitly not automated claim decisioning"));
check("Manifest links voiceover timing doc", manifest.includes("docs/agrifabric-static-demo-voiceover-timing.md"));
check("Backlog links voiceover timing doc", backlog.includes("docs/agrifabric-static-demo-voiceover-timing.md"));
check("Docs README links voiceover timing doc", docsReadme.includes("agrifabric-static-demo-voiceover-timing.md"));

const requiredTimingSections = [
  "V02 - Six pillars of AgriFabric",
  "V10 - Relationship graph and commercial analytics",
  "V08 - PIN, GPS, DigiPin, and land intelligence",
  "V11 - Insurance and subsidy integrity foundation",
  "Never say detects fraud today",
];

for (const section of requiredTimingSections) {
  check(`Timing doc includes: ${section}`, timing.includes(section));
}

const healthy = process.exitCode !== 1;

console.log("========================================================================");
console.log(healthy ? "AGRIFABRIC STATIC DEMO READINESS CHECK PASSED" : "AGRIFABRIC STATIC DEMO READINESS CHECK FAILED");
console.log("========================================================================");

process.exit(healthy ? 0 : 1);
