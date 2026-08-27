#!/usr/bin/env python3
"""Read-only plan for using NWDP village boundaries to reduce CoRE/agro-zone ambiguity."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def build_plan() -> dict:
    return {
        "schema_version": "nwdp_boundary_core_agro_zone_ambiguity_reduction_plan.v1",
        "mode": "READ_ONLY_CORE_AGRO_ZONE_AMBIGUITY_REDUCTION_PLAN",
        "healthy": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": (
            "Design plan only. NWDP village boundary polygons can reduce earlier CoRE/agro-climatic "
            "or agro-ecological ambiguity by moving classification from coarse admin areas to "
            "village-polygon overlay. This plan does not classify villages, write mappings, enable "
            "runtime lookup, or change Android behavior."
        ),
        "input_layers": {
            "existing_geography_master": {
                "table": "geography_villages",
                "known_count": 576083,
                "known_lgd_code_count": 576082,
                "role": "Existing Android/admin state-district-tehsil-village selection hierarchy.",
            },
            "nwdp_boundary_staging": {
                "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
                "candidate_table": "geography_boundary_crosswalk_candidates",
                "source_feature_table": "geography_boundary_source_features",
                "staged_candidate_count": 654285,
                "safe_direct_auto_candidate_count": 313667,
                "future_match_ready_candidate_count": 453036,
                "role": "Village polygon boundary layer for matched master villages.",
            },
            "core_or_agro_zone_layer": {
                "required": True,
                "examples": [
                    "CoRE agro-climatic zone polygons",
                    "agro-ecological zone polygons",
                    "district/block-to-zone rules with polygon fallback",
                ],
                "role": "Target classification layer to intersect against NWDP village polygons.",
            },
        },
        "overlay_method": {
            "unit_of_analysis": "master village with eligible/matched NWDP polygon",
            "operation": "area-weighted polygon intersection",
            "candidate_selection": {
                "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
                "candidate_bucket": "DIRECT_VLCODE_MATCH",
                "review_status": "AUTO_CANDIDATE",
                "required_is_active": False,
                "required_promotion_status": "NOT_PROMOTED",
                "requires_proposed_village_id": True,
            },
            "classification_rules": {
                "dominant_zone_threshold": 0.80,
                "review_zone_threshold_min": 0.50,
                "safe_classification": "single zone overlap >= dominant_zone_threshold",
                "manual_review_classification": "top zone overlap >= review_zone_threshold_min and < dominant_zone_threshold",
                "unresolved_classification": "multiple close overlaps, missing polygon, invalid geometry, or no zone overlap",
            },
            "area_audit_required": True,
        },
        "expected_outputs": {
            "read_only_summary_json": True,
            "state_wise_counts": True,
            "zone_wise_counts": True,
            "village_level_samples": True,
            "previously_ambiguous_count": True,
            "reduced_to_dominant_zone_count": True,
            "still_multi_zone_unresolved_count": True,
            "missing_or_unmatched_boundary_count": True,
            "manual_review_queue_count": True,
        },
        "why_this_reduces_ambiguity": {
            "previous_problem": (
                "Coarse admin units such as districts, tehsils, or blocks can span multiple agro/climatic zones, "
                "making one-zone assignment unsafe."
            ),
            "nwdp_improvement": (
                "Matched NWDP village polygons let the system compute village-level area overlap against "
                "zone polygons, so many coarse multi-zone cases can become dominant-zone village candidates."
            ),
            "remaining_limits": [
                "NWDP boundaries do not contain climate/agro-zone meaning by themselves.",
                "A target zone polygon/rule layer is still required.",
                "Villages genuinely spanning multiple zones may remain unresolved.",
                "Manual-review and blocked NWDP candidates must remain excluded from auto-classification.",
            ],
        },
        "guardrails": {
            "db_writes_attempted": False,
            "core_zone_mappings_written": False,
            "nwdp_candidates_activated": False,
            "nwdp_candidates_promoted": False,
            "project_matching_records_written": False,
            "runtime_tables_written": False,
            "runtime_spatial_matching_changed": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
        "readiness": {
            "ready_for_read_only_overlay_analysis": True,
            "ready_for_core_zone_mapping_apply": False,
            "ready_for_android_behavior_change": False,
            "ready_for_lookup_api_enablement": False,
            "ready_for_runtime_spatial_matching": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/nwdp-boundary-core-agro-zone-ambiguity-reduction-plan.json"))
    args = parser.parse_args()

    plan = build_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "healthy": plan["healthy"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
