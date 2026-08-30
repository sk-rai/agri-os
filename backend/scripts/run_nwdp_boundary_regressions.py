#!/usr/bin/env python3
"""Run NWDP boundary staging/admin regressions in order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PYTHON = ROOT / "venv" / "bin" / "python"

CHECKS = [
    ("verify inactive staging import", [str(PYTHON), "scripts/verify_nwdp_boundary_review_staging_import.py"]),
    ("admin read endpoints", [str(PYTHON), "scripts/test_nwdp_boundary_admin_read_endpoints.py"]),
    ("admin review endpoint", [str(PYTHON), "scripts/test_nwdp_boundary_admin_review_endpoint.py"]),
    ("runtime tiny pilot apply", [str(PYTHON), "scripts/test_nwdp_boundary_runtime_tiny_pilot_apply.py"]),
    ("runtime pilot inspection", [str(PYTHON), "scripts/test_nwdp_boundary_runtime_pilot_inspection.py"]),
    ("runtime activation plan", [str(PYTHON), "scripts/test_nwdp_boundary_runtime_activation_plan.py"]),
    ("all-state inactive staging import plan", [str(PYTHON), "scripts/test_nwdp_boundary_all_state_inactive_staging_import_plan.py"]),
    ("all-state inactive staging importer", [str(PYTHON), "scripts/test_nwdp_boundary_all_state_inactive_staging_importer.py"]),
    ("all-state Chandigarh inactive staging apply", [str(PYTHON), "scripts/test_nwdp_boundary_all_state_chandigarh_inactive_staging_apply.py"]),
    ("admin state-wise match summary endpoint", [str(PYTHON), "scripts/test_nwdp_boundary_admin_state_wise_match_summary_endpoint.py"]),
    ("project matching enablement plan", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_enablement_plan.py"]),
    ("project matching read model plan", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_read_model_plan.py"]),
    ("project matching eligible candidates endpoint", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_eligible_candidates_endpoint.py"]),
    ("boundary review UI project matching reuse", [str(PYTHON), "scripts/test_nwdp_boundary_review_ui_project_matching_reuse.py"]),
    ("project matching project preview plan", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_project_preview_plan.py"]),
    ("project matching project preview endpoint", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_project_preview_endpoint.py"]),
    ("project matching project preview positive coverage", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_project_preview_positive_coverage.py"]),
    ("project matching apply dry-run plan", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_apply_dry_run_plan.py"]),
    ("project matching apply dry-run positive selection", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_apply_dry_run_positive_selection.py"]),
    ("project matching apply design plan", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_apply_design_plan.py"]),
    ("project match schema migration", [str(PYTHON), "scripts/test_nwdp_boundary_project_match_schema_migration.py"]),
    ("project matching apply disabled endpoint", [str(PYTHON), "scripts/test_nwdp_boundary_project_matching_apply_disabled_endpoint.py"]),
    ("core agro-zone ambiguity reduction plan", [str(PYTHON), "scripts/test_nwdp_boundary_core_agro_zone_ambiguity_reduction_plan.py"]),
    ("core agro-zone overlay feasibility", [str(PYTHON), "scripts/test_nwdp_core_agro_zone_overlay_feasibility.py"]),
    ("core agro-zone sample overlay", [str(PYTHON), "scripts/test_nwdp_core_agro_zone_sample_overlay.py"]),
    ("core agro-zone pilot overlay report", [str(PYTHON), "scripts/test_nwdp_core_agro_zone_pilot_overlay_report.py"]),
    ("core agro-zone national sample overlay report", [str(PYTHON), "scripts/test_nwdp_core_agro_zone_national_sample_overlay_report.py"]),
    ("core agro-zone full overlay Chandigarh", [str(PYTHON), "scripts/test_nwdp_core_agro_zone_full_overlay_chandigarh.py"]),
("core agro-zone full national summary", [str(PYTHON), "scripts/test_nwdp_core_agro_zone_full_national_summary.py"]),
    ("nwdp demographic enrichment readiness", [str(PYTHON), "scripts/test_nwdp_demographic_enrichment_readiness.py"]),
    ("nwdp demographic enrichment schema plan", [str(PYTHON), "scripts/test_nwdp_demographic_enrichment_schema_plan.py"]),
("nwdp demographic enrichment schema migration plan", [str(PYTHON), "scripts/test_nwdp_demographic_enrichment_schema_migration_plan.py"]),
("nwdp demographic enrichment schema migration file", [str(PYTHON), "scripts/test_nwdp_demographic_enrichment_schema_migration_file.py"]),
("nwdp demographic schema migration apply validation plan", [str(PYTHON), "scripts/test_nwdp_demographic_schema_migration_apply_validation_plan.py"]),
("nwdp demographic schema migration db state", [str(PYTHON), "scripts/test_nwdp_demographic_schema_migration_db_state.py"]),
("nwdp demographic admin preview endpoint plan", [str(PYTHON), "scripts/test_nwdp_demographic_admin_preview_endpoint_plan.py"]),
("nwdp demographic admin preview endpoint", [str(PYTHON), "scripts/test_nwdp_demographic_admin_preview_endpoint.py"]),
    ("nwdp demographic enrichment import plan", [str(PYTHON), "scripts/test_nwdp_demographic_enrichment_import_plan.py"]),
    ("nwdp demographic profile import apply disabled", [str(PYTHON), "scripts/test_nwdp_demographic_profile_import_apply_disabled.py"]),
]


def main() -> int:
    print("=" * 72)
    print("NWDP BOUNDARY REGRESSION RUNNER")
    print("=" * 72)

    for label, command in CHECKS:
        print(f"\n--- {label} ---")
        result = subprocess.run(command, cwd=BACKEND, text=True, capture_output=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            print(f"FAILED: {label}")
            return result.returncode

    print("=" * 72)
    print("NWDP BOUNDARY REGRESSION RUNNER PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
