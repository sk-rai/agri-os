#!/usr/bin/env python3
"""Regression for read-only all-state sampled NWDP × CoRE/agro-zone overlay report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/pilot_nwdp_core_agro_zone_overlay_report.py"
OUTPUT = Path("/tmp/nwdp-core-agro-zone-national-sample-overlay-report-regression.json")

sys.path.insert(0, str(BACKEND))
from app.core.config import settings


def db_url() -> str:
    return str(
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def staged_states() -> list[str]:
    engine = create_engine(db_url())
    with engine.connect() as conn:
        rows = conn.execute(text("""
            select distinct b.state_or_ut
            from geography_boundary_import_batches b
            join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
            where b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.review_status = 'AUTO_CANDIDATE'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_village_id is not null
            order by b.state_or_ut
        """)).scalars().all()
    return [str(row) for row in rows]


def main() -> int:
    if OUTPUT.exists():
        OUTPUT.unlink()

    states = staged_states()
    check(len(states) == 36, "All staged states/UTs have eligible overlay candidates", states)

    command = [
        str(PYTHON),
        str(SCRIPT),
        "--states",
        *states,
        "--limit-per-state",
        "5",
        "--samples-per-state",
        "1",
        "--output",
        str(OUTPUT),
    ]
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "National sample overlay report writes output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))

    check(proc.returncode == 0, "National sample overlay report exits zero", data)
    check(data["schema_version"] == "nwdp_core_agro_zone_pilot_overlay_report.v1", "Schema version is stable", data)
    check(data["mode"] == "READ_ONLY_MULTI_STATE_POLYGON_OVERLAY_PILOT_REPORT", "National sample report is read-only", data)
    check(data["healthy"] is True, "National sample report is healthy", data)
    check(data["nwdp_source_crs"] == "EPSG:7755", "NWDP source CRS is explicit", data)
    check(data["nwdp_target_crs"] == "EPSG:4326", "NWDP target CRS is WGS84", data)
    check(data["area_crs"] == "EPSG:6933", "Overlay uses equal-area CRS", data)

    aggregate = data["aggregate"]
    check(aggregate["state_count"] == 36, "National sample covers 36 states/UTs", aggregate)
    check(aggregate["healthy_state_count"] == 36, "All sampled states/UTs are healthy", aggregate)
    check(0 < aggregate["candidate_count"] <= 180, "National sample reads up to 5 candidates per state/UT", aggregate)
    check(aggregate["sample_count"] == aggregate["candidate_count"], "National sample overlays every sampled candidate", aggregate)

    layer_counts = aggregate["layer_status_counts"]
    check(layer_counts["agro_climatic"].get("DOMINANT_ZONE", 0) > 0, "Agro-climatic layer produces dominant zones", layer_counts)
    check(layer_counts["agro_ecological"].get("DOMINANT_ZONE", 0) > 0, "Agro-ecological layer produces dominant zones", layer_counts)
    check(layer_counts["biogeographic"].get("DOMINANT_ZONE", 0) > 0, "Biogeographic layer produces dominant zones", layer_counts)

    check(all(0 < state["sample_count"] <= 5 for state in data["states"]), "Each state/UT has up to five sampled overlays", data["states"])
    check(all(state["summary"]["invalid_or_missing_geometry_count"] == 0 for state in data["states"]), "No sampled state has invalid/missing geometry", data["states"])

    guardrails = data["guardrails"]
    check(guardrails["db_writes_attempted"] is False, "National sample attempts no DB writes", guardrails)
    check(guardrails["core_zone_mappings_written"] is False, "National sample writes no CoRE mappings", guardrails)
    check(guardrails["nwdp_candidates_activated"] is False, "National sample does not activate NWDP candidates", guardrails)
    check(guardrails["nwdp_candidates_promoted"] is False, "National sample does not promote NWDP candidates", guardrails)
    check(guardrails["project_matching_records_written"] is False, "National sample writes no project matches", guardrails)
    check(guardrails["runtime_tables_written"] is False, "National sample writes no runtime tables", guardrails)
    check(guardrails["lookup_api_enabled"] is False, "National sample keeps lookup disabled", guardrails)
    check(guardrails["android_behavior_changed"] is False, "National sample keeps Android unchanged", guardrails)

    readiness = data["readiness"]
    check(readiness["ready_for_read_only_national_overlay_report"] is True, "Ready for larger read-only national report", readiness)
    check(readiness["ready_for_core_zone_mapping_apply"] is False, "Not mapping apply", readiness)
    check(readiness["ready_for_android_behavior_change"] is False, "Android unchanged", readiness)

    print("=" * 72)
    print("NWDP CORE AGRO-ZONE NATIONAL SAMPLE OVERLAY REPORT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
