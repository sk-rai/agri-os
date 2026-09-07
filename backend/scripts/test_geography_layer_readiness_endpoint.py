#!/usr/bin/env python3
"""Regression for read-only geography layer readiness endpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin  # noqa: E402


ENDPOINT = "/api/v1/master-data/geography/layer-readiness"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2400])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("GEOGRAPHY LAYER READINESS ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None

    try:
        unauth = client.get(ENDPOINT)
        check(unauth.status_code in (401, 403), "Unauthenticated readiness endpoint is denied", unauth.text)

        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")

        response = client.get(ENDPOINT, headers=headers)
        check(response.status_code == 200, "Admin can read readiness endpoint", response.text)

        data = response.json()
        summary = data["summary"]
        gap = data["gap_accounting"]

        check(data["schema_version"] == "geography_layer_readiness_matrix.v1", "Schema version is stable", data)
        check(data["mode"] == "READ_ONLY_STATE_DISTRICT_GEOGRAPHY_LAYER_READINESS_MATRIX", "Endpoint is read-only matrix", data)
        check(data["healthy"] is True, "Endpoint is healthy", data)
        check(len(data["rows"]) > 0, "Endpoint returns rows", data["rows"][:2])

        check(summary["state_district_row_count"] > 0, "State/district row count is visible", summary)
        check(summary["lgd_village_count"] >= 500000, "LGD village coverage is visible", summary)
        check(summary["pin_linked_village_count"] >= 500000, "PIN-code coverage is visible", summary)
        check(summary["demographic_active_promoted_count"] >= 450000, "NWDP demographic admin layer is visible", summary)
        check(summary["demographic_remaining_eligible_count"] == 0, "No demographic rows remain promotion-eligible", summary)
        check(summary["boundary_candidate_count"] >= 550000, "District-placeable boundary candidates are visible", summary)

        check(gap["boundary_candidate_raw_count"] >= summary["boundary_candidate_count"], "Boundary raw count covers matrix count", gap)
        check(gap["boundary_candidate_outside_state_district_matrix_count"] > 0, "Boundary outside-matrix gap is exposed", gap)
        check(gap["demographic_profile_outside_state_district_matrix_count"] == 0, "Demographic profiles are fully placeable", gap)
        check(gap["pin_link_outside_state_district_matrix_count"] == 0, "PIN links are fully placeable", gap)

        boundary_geometry = data["boundary_geometry_validation_readiness"]
        boundary_geometry_summary = boundary_geometry["summary"]
        check(boundary_geometry_summary["candidate_count"] > 0, "Boundary geometry candidate count is visible", boundary_geometry_summary)
        check(boundary_geometry_summary["invalid_geometry_count"] > 0, "Boundary invalid geometry blockers are visible", boundary_geometry_summary)
        check(boundary_geometry_summary["not_runtime_eligible_source_count"] > 0, "Boundary runtime-ineligible source blockers are visible", boundary_geometry_summary)
        check(boundary_geometry_summary["selected_runtime_promotable_count"] == 0, "Boundary geometry confirms no selected runtime promotable rows", boundary_geometry_summary)
        check(boundary_geometry["readiness"]["ready_for_admin_geometry_review"] is True, "Boundary geometry admin review is ready", boundary_geometry["readiness"])
        check(boundary_geometry["readiness"]["ready_for_geometry_repair_plan"] is True, "Boundary geometry repair planning is ready", boundary_geometry["readiness"])
        check(boundary_geometry["readiness"]["ready_for_selected_runtime_promotion_apply"] is False, "Boundary geometry runtime apply remains disabled", boundary_geometry["readiness"])
        check(boundary_geometry["guardrails"]["db_writes_attempted"] is False, "Boundary geometry rollup writes no DB rows", boundary_geometry["guardrails"])
        check(boundary_geometry["guardrails"]["geometry_repair_attempted"] is False, "Boundary geometry rollup repairs no geometry", boundary_geometry["guardrails"])
        check(boundary_geometry["guardrails"]["runtime_lookup_enabled"] is False, "Boundary geometry rollup keeps runtime lookup disabled", boundary_geometry["guardrails"])
        check(boundary_geometry["guardrails"]["android_behavior_changed"] is False, "Boundary geometry rollup keeps Android unchanged", boundary_geometry["guardrails"])

        boundary_repair = data["boundary_geometry_repair_classification"]
        boundary_repair_summary = boundary_repair["summary"]
        check(boundary_repair_summary["candidate_count"] > 0, "Boundary repair classification candidate count is visible", boundary_repair_summary)
        check(boundary_repair_summary["invalid_or_unknown_geometry_count"] > 0, "Boundary repair classification geometry work is visible", boundary_repair_summary)
        check(boundary_repair_summary["runtime_ineligible_source_count"] > 0, "Boundary repair classification runtime eligibility work is visible", boundary_repair_summary)
        check(boundary_repair_summary["validate_geometry_and_runtime_eligibility_count"] > 0, "Boundary repair classification combined validation bucket is visible", boundary_repair_summary)
        check(boundary_repair_summary["no_repair_needed_runtime_promotable_count"] == 0, "Boundary repair classification confirms no promotable rows", boundary_repair_summary)
        check(boundary_repair["readiness"]["ready_for_admin_repair_planning"] is True, "Boundary repair planning is admin-ready", boundary_repair["readiness"])
        check(boundary_repair["readiness"]["ready_for_geometry_validation_pipeline_design"] is True, "Boundary validation pipeline design is ready", boundary_repair["readiness"])
        check(boundary_repair["readiness"]["ready_for_selected_runtime_promotion_apply"] is False, "Boundary repair classification apply remains disabled", boundary_repair["readiness"])
        check(boundary_repair["guardrails"]["db_writes_attempted"] is False, "Boundary repair classification writes no DB rows", boundary_repair["guardrails"])
        check(boundary_repair["guardrails"]["geometry_repair_attempted"] is False, "Boundary repair classification repairs no geometry", boundary_repair["guardrails"])
        check(boundary_repair["guardrails"]["geometry_validation_status_changed"] is False, "Boundary repair classification changes no validation status", boundary_repair["guardrails"])
        check(boundary_repair["guardrails"]["source_runtime_eligibility_changed"] is False, "Boundary repair classification changes no runtime eligibility", boundary_repair["guardrails"])
        check(boundary_repair["guardrails"]["runtime_lookup_enabled"] is False, "Boundary repair classification keeps runtime lookup disabled", boundary_repair["guardrails"])
        check(boundary_repair["guardrails"]["android_behavior_changed"] is False, "Boundary repair classification keeps Android unchanged", boundary_repair["guardrails"])

        repair_events = data["boundary_geometry_repair_events"]
        repair_event_summary = repair_events["summary"]
        check(
            isinstance(
                repair_event_summary["repair_event_table_present"],
                bool,
            ),
            "Boundary repair event table presence is readable",
            repair_event_summary,
        )
        check(
            repair_event_summary["repair_event_count"] >= 0,
            "Boundary repair event count is readable",
            repair_event_summary,
        )
        check(
            repair_event_summary["active_repair_event_count"] >= 0,
            "Active boundary repair event count is readable",
            repair_event_summary,
        )
        check(
            repair_event_summary["rolled_back_repair_event_count"] >= 0,
            "Rolled-back boundary repair event count is readable",
            repair_event_summary,
        )
        check(
            repair_events["readiness"][
                "ready_for_broad_geometry_repair_apply"
            ] is False,
            "Broad boundary geometry repair remains disabled",
            repair_events["readiness"],
        )
        check(
            repair_events["readiness"][
                "ready_for_selected_runtime_promotion_apply"
            ] is False,
            "Repair events do not enable runtime promotion",
            repair_events["readiness"],
        )
        check(
            repair_events["guardrails"]["db_writes_attempted"] is False,
            "Boundary repair event rollup is read-only",
            repair_events["guardrails"],
        )
        check(
            repair_events["guardrails"]["runtime_lookup_enabled"] is False,
            "Boundary repair events keep runtime lookup disabled",
            repair_events["guardrails"],
        )
        check(
            repair_events["guardrails"]["android_behavior_changed"] is False,
            "Boundary repair events keep Android unchanged",
            repair_events["guardrails"],
        )

        project_boundary = data["project_boundary_readiness"]
        project_boundary_summary = project_boundary["summary"]
        check(project_boundary_summary["active_project_count"] >= 0, "Project boundary active project count is visible", project_boundary_summary)
        check(project_boundary_summary["raw_boundary_candidate_count"] > 0, "Project boundary raw candidates are visible", project_boundary_summary)
        check(project_boundary_summary["raw_eligible_boundary_candidate_count"] > 0, "Project boundary eligible candidates are visible", project_boundary_summary)
        check(project_boundary_summary["projects_with_resolved_scope_count"] >= 0, "Project boundary resolved project scope count is visible", project_boundary_summary)
        check(project_boundary_summary["projects_ready_for_project_boundary_dry_run_count"] >= 0, "Project boundary dry-run project count is visible", project_boundary_summary)
        check(project_boundary["readiness"]["ready_for_project_boundary_apply"] is False, "Project boundary apply remains disabled", project_boundary["readiness"])
        check(project_boundary["readiness"]["ready_for_runtime_spatial_matching"] is False, "Project boundary runtime spatial matching remains disabled", project_boundary["readiness"])
        check(project_boundary["readiness"]["ready_for_android_behavior_change"] is False, "Project boundary keeps Android unchanged", project_boundary["readiness"])

        selected_runtime = data["selected_boundary_runtime_promotion_readiness"]
        selected_summary = selected_runtime["summary"]
        check(selected_summary["candidate_count"] >= 0, "Selected boundary runtime candidate count is visible", selected_summary)
        check(selected_summary["invalid_geometry_count"] >= 0, "Selected boundary invalid geometry blockers are visible", selected_summary)
        check(selected_summary["not_runtime_eligible_source_count"] >= 0, "Selected boundary runtime eligibility blockers are visible", selected_summary)
        check(selected_summary["existing_runtime_feature_count"] >= 0, "Existing runtime feature count is visible", selected_summary)
        check(selected_runtime["readiness"]["ready_for_selected_runtime_promotion_apply"] is False, "Selected boundary runtime apply remains disabled", selected_runtime["readiness"])
        check(selected_runtime["readiness"]["ready_for_runtime_lookup_enablement"] is False, "Selected boundary runtime lookup remains disabled", selected_runtime["readiness"])
        check(selected_runtime["readiness"]["ready_for_android_behavior_change"] is False, "Selected boundary runtime keeps Android unchanged", selected_runtime["readiness"])
        check(selected_runtime["guardrails"]["db_writes_attempted"] is False, "Selected boundary runtime rollup is read-only", selected_runtime["guardrails"])

        external_api = data["external_api_readiness"]
        external_summary = external_api["summary"]
        check(external_summary["provider_surface_count"] >= 1, "External API provider surfaces are visible", external_summary)
        check(external_summary["weather_provider_config_count"] >= 0, "Weather provider config count is visible", external_summary)
        check(external_summary["soil_provider_surface_count"] >= 1, "Soil provider surface count is visible", external_summary)
        check(external_summary["weather_snapshot_count"] >= 0, "Weather snapshot count is visible", external_summary)
        check(external_summary["soil_enrichment_snapshot_count"] >= 0, "Soil enrichment snapshot count is visible", external_summary)
        check(external_api["readiness"]["ready_for_admin_review"] is True, "External API readiness is admin-visible", external_api["readiness"])
        check(external_api["readiness"]["ready_for_android_behavior_change"] is False, "External API keeps Android unchanged", external_api["readiness"])
        check(external_api["readiness"]["requires_live_execution_policy_approval"] is True, "External API live execution approval is required", external_api["readiness"])
        check(external_api["guardrails"]["external_api_called"] is False, "Endpoint makes no external API calls", external_api["guardrails"])
        check(external_api["guardrails"]["provider_worker_executed"] is False, "Endpoint runs no provider workers", external_api["guardrails"])
        check(external_api["guardrails"]["provider_live_execution_enabled"] is False, "Endpoint enables no provider live execution", external_api["guardrails"])
        check(external_api["guardrails"]["android_behavior_changed"] is False, "External API rollup keeps Android unchanged", external_api["guardrails"])

        posture = data["source_posture"]
        check(posture["lgd_is_canonical_runtime_identity"] is True, "LGD remains canonical runtime identity", posture)
        check(posture["village_pin_codes_android_ready"] is True, "PIN-code layer remains Android-ready", posture)
        check(posture["nwdp_demographic_android_enabled"] is False, "NWDP demographic remains Android-disabled", posture)
        check(posture["nwdp_boundary_runtime_lookup_enabled"] is False, "NWDP boundary runtime lookup remains disabled", posture)
        check(posture["soi_direct_lgd_join_safe"] is False, "SOI direct LGD join remains unsafe", posture)

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Endpoint attempts no DB writes", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Endpoint does not enable runtime lookup", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Endpoint does not change Android behavior", guardrails)

        scoped = client.get(
        ENDPOINT + "?state_or_ut=Andaman%20And%20Nicobar%20Islands&district=Nicobars&limit=5",
        headers=headers,
        )
        check(scoped.status_code == 200, "Scoped readiness endpoint returns 200", scoped.text)
        scoped_data = scoped.json()
        check(scoped_data["filters"]["district"] == "Nicobars", "Scoped endpoint records district filter", scoped_data["filters"])
        check(len(scoped_data["rows"]) <= 5, "Scoped endpoint honors limit", scoped_data["rows"])

        print("=" * 72)
        print("GEOGRAPHY LAYER READINESS ENDPOINT REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
