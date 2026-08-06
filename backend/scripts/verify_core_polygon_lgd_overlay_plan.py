#!/usr/bin/env python3
"""Verify the CoRE polygon/LGD overlay planning artifacts are in place.

Read-only. This deliberately does not require local CoRE exports or boundary
geometry, because the current milestone is planning/readiness, not overlay
execution.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

REQUIRED_ARTIFACTS = [
    "backend/scripts/audit_climate_polygon_overlay_readiness.py",
    "backend/scripts/plan_core_polygon_lgd_overlay.py",
    "backend/scripts/verify_core_polygon_lgd_overlay_plan.py",
    "docs/core-stack-gee-export-checklist.md",
    "docs/lgd-boundary-source-checklist.md",
    "docs/core-polygon-lgd-overlay-plan.md",
    "docs/crop-climate-suitability-roadmap.md",
]

REQUIRED_DOC_PHRASES = {
    "docs/core-polygon-lgd-overlay-plan.md": [
        "Android must not call Google Earth Engine",
        "No Android Maestro flow is required for this planning step",
        "geography_climate_region_mappings",
    ],
    "docs/crop-climate-suitability-roadmap.md": [
        "CoRE polygon/LGD overlay execution plan",
    ],
}


def run_plan() -> dict:
    output = subprocess.check_output(
        [sys.executable, str(BACKEND / "scripts/plan_core_polygon_lgd_overlay.py")],
        text=True,
    )
    return json.loads(output)


def main() -> int:
    missing = [path for path in REQUIRED_ARTIFACTS if not (ROOT / path).exists()]
    phrase_failures = []
    for rel_path, phrases in REQUIRED_DOC_PHRASES.items():
        path = ROOT / rel_path
        text = path.read_text() if path.exists() else ""
        for phrase in phrases:
            if phrase not in text:
                phrase_failures.append({"path": rel_path, "missing_phrase": phrase})

    plan = run_plan()
    readiness = {
        "required_artifacts_present": not missing,
        "plan_script_runs": plan.get("schema_version") == "core_polygon_lgd_overlay_plan.v1",
        "plan_is_read_only": not plan.get("external_calls_made") and not plan.get("db_writes_made"),
        "android_maestro_required_now": bool(
            plan.get("android_impact", {}).get("maestro_required_now"),
        ),
        "android_maestro_correctly_not_required_now": not bool(
            plan.get("android_impact", {}).get("maestro_required_now"),
        ),
        "required_doc_phrases_present": not phrase_failures,
    }
    result = {
        "schema_version": "core_polygon_lgd_overlay_plan_verification.v1",
        "missing_artifacts": missing,
        "phrase_failures": phrase_failures,
        "plan_summary": {
            "mode": plan.get("mode"),
            "required_core_exports": len(plan.get("required_core_exports", [])),
            "overlay_phases": len(plan.get("overlay_phases", [])),
            "android_impact": plan.get("android_impact", {}),
        },
        "readiness": readiness,
    }
    required_ready = [
        readiness["required_artifacts_present"],
        readiness["plan_script_runs"],
        readiness["plan_is_read_only"],
        readiness["android_maestro_correctly_not_required_now"],
        readiness["required_doc_phrases_present"],
    ]
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(required_ready) else 1


if __name__ == "__main__":
    raise SystemExit(main())
