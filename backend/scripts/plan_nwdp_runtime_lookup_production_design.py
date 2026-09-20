#!/usr/bin/env python3
"""Design-only NWDP production runtime point lookup contract."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUNTIME_MIGRATION = (
    ROOT
    / "backend/alembic/versions/"
    / "055_add_nwdp_boundary_runtime_tables.py"
)
PROJECT_MIGRATION = (
    ROOT
    / "backend/alembic/versions/"
    / "056_add_nwdp_boundary_project_matches.py"
)
GEOGRAPHY_API = (
    ROOT
    / "backend/app/modules/master_data/api/"
    / "geography.py"
)
PREVIEW_SCRIPT = (
    ROOT
    / "backend/scripts/"
    / "preview_nwdp_runtime_point_lookup.py"
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def contains(
    path: Path,
    marker: str,
) -> bool:
    return (
        path.exists()
        and marker
        in path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )


def main() -> int:
    options = arguments()

    reuse_evidence = {
        "runtime_feature_table_exists": contains(
            RUNTIME_MIGRATION,
            "geography_boundary_runtime_features",
        ),
        "runtime_crosswalk_table_exists": contains(
            RUNTIME_MIGRATION,
            "geography_boundary_runtime_crosswalks",
        ),
        "runtime_geometry_jsonb_exists": contains(
            RUNTIME_MIGRATION,
            '"geometry_wgs84"',
        ),
        "project_assignment_table_exists": contains(
            PROJECT_MIGRATION,
            "geography_boundary_project_matches",
        ),
        "admin_view_authorization_exists": contains(
            GEOGRAPHY_API,
            "AdminPermission.VIEW",
        ),
        "project_scope_resolver_exists": contains(
            GEOGRAPHY_API,
            "_build_project_boundary_scope_village_sql",
        ),
        "assignment_payload_exists": contains(
            GEOGRAPHY_API,
            "_project_boundary_assignment_payload",
        ),
        "assignment_guardrails_exist": contains(
            GEOGRAPHY_API,
            "_project_boundary_assignment_guardrails",
        ),
        "lookup_remains_disabled": contains(
            GEOGRAPHY_API,
            '"lookup_api_enabled": False',
        ),
        "st_covers_preview_proven": contains(
            PREVIEW_SCRIPT,
            "ST_Covers",
        ),
        "preview_is_read_only": contains(
            PREVIEW_SCRIPT,
            "READ_ONLY_10_ROW_POINT_LOOKUP_PREVIEW",
        ),
    }

    design = {
        "schema_version":
            "nwdp_runtime_lookup_production_design.v1",
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
        "healthy": all(reuse_evidence.values()),
        "status": "DESIGNED_NOT_AUTHORIZED",
        "mode": "READ_ONLY_PRODUCTION_LOOKUP_DESIGN",
        "scope": {
            "current_runtime_scope":
                "ACTIVE_KARNATAKA_10_ROW_PILOT",
            "production_scope":
                "ACTIVE_RUNTIME_SETS_ONLY",
            "database_writes_attempted": False,
            "migration_applied": False,
            "geometry_backfill_started": False,
            "endpoint_implemented": False,
            "lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "reuse_evidence": reuse_evidence,
        "reuse_decision": {
            "reuse_runtime_set_identity": True,
            "reuse_runtime_feature_identity": True,
            "reuse_runtime_crosswalk_identity": True,
            "reuse_village_crosswalks": True,
            "reuse_st_covers_predicate": True,
            "reuse_admin_view_authorization": True,
            "reuse_project_scope_resolver": True,
            "reuse_assignment_audit_pattern": True,
            "reuse_activation_and_rollback_governance": True,
            "reuse_jsonb_geometry_for_production": False,
            "reuse_preview_endpoint_as_production_endpoint": False,
        },
        "storage_design": {
            "table":
                "geography_boundary_runtime_features",
            "existing_geometry_column": {
                "name": "geometry_wgs84",
                "type": "jsonb",
                "production_lookup_role":
                    "LINEAGE_ONLY_AFTER_MIGRATION",
            },
            "new_geometry_column": {
                "name": "geometry_wgs84_geom",
                "type": "geometry(Geometry,4326)",
                "initially_nullable": True,
                "allowed_geometry_types": [
                    "ST_Polygon",
                    "ST_MultiPolygon",
                ],
                "required_for_active_lookup_rows": True,
                "source":
                    "checksum-pinned normalized GeoJSON",
                "identity_join":
                    "runtime_feature.source_feature_id",
            },
            "constraints": [
                (
                    "SRID must equal 4326 whenever "
                    "geometry_wgs84_geom is non-null"
                ),
                (
                    "geometry type must be Polygon or "
                    "MultiPolygon"
                ),
                (
                    "active lookup rows require non-empty "
                    "valid geometry"
                ),
            ],
            "index": {
                "name":
                    "idx_boundary_runtime_features_geom_active",
                "method": "GIST",
                "expression": "geometry_wgs84_geom",
                "predicate": (
                    "is_active = true and "
                    "geometry_wgs84_geom is not null"
                ),
            },
            "migration_strategy": [
                "Add nullable native PostGIS geometry column",
                "Add geometry type and SRID constraints",
                "Create partial GiST index concurrently",
                (
                    "Do not populate geometry inside the "
                    "schema migration"
                ),
                (
                    "Require separate checksum-pinned, "
                    "authorized, restartable backfill"
                ),
                (
                    "Require reconciliation before lookup "
                    "enablement"
                ),
            ],
        },
        "lookup_query_design": {
            "spatial_predicate": "ST_Covers",
            "prefilter":
                "geometry_wgs84_geom && ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)",
            "required_filters": [
                "runtime set is active",
                "runtime feature is active",
                "runtime crosswalk is active",
                "runtime scope equals village",
                "geometry validation status equals VALIDATED",
                "source feature remains runtime eligible",
                "native geometry is non-null",
            ],
            "result_policy": {
                "zero_matches": "UNMATCHED",
                "one_match": "MATCHED",
                "multiple_matches":
                    "AMBIGUOUS_CONFLICT_NO_AUTOMATIC_SELECTION",
                "boundary_behavior":
                    "ST_Covers includes polygon boundaries",
                "deterministic_order": [
                    "runtime_set_id",
                    "runtime_feature_id",
                ],
            },
        },
        "api_contract": {
            "method": "GET",
            "path":
                "/geography/nwdp-boundary-runtime/point-lookup",
            "authorization": {
                "initial_permission":
                    "AdminPermission.VIEW",
                "project_scoped": False,
                "public_or_android_access": False,
            },
            "query": {
                "latitude": {
                    "type": "number",
                    "minimum": -90,
                    "maximum": 90,
                    "required": True,
                },
                "longitude": {
                    "type": "number",
                    "minimum": -180,
                    "maximum": 180,
                    "required": True,
                },
                "runtime_set_id": {
                    "type": "uuid",
                    "required": False,
                    "default":
                        "current active runtime set",
                },
            },
            "response": {
                "schema_version":
                    "nwdp_boundary_runtime_point_lookup.v1",
                "fields": [
                    "status",
                    "point",
                    "match_count",
                    "runtime_set_id",
                    "runtime_feature_id",
                    "runtime_crosswalk_id",
                    "village_id",
                    "village_lgd_code",
                    "runtime_scope",
                    "geometry_hash",
                ],
                "geometry_returned": False,
            },
            "errors": {
                "400":
                    "invalid coordinates or request",
                "403":
                    "admin permission required",
                "409":
                    "multiple active polygons cover point",
                "503":
                    "lookup feature flag disabled or runtime set unavailable",
            },
        },
        "enablement_design": {
            "feature_flag": {
                "name":
                    "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED",
                "default": False,
                "fail_closed": True,
                "server_side_only": True,
            },
            "phases": [
                {
                    "phase": 1,
                    "name": "SCHEMA_ONLY",
                    "lookup_enabled": False,
                },
                {
                    "phase": 2,
                    "name":
                        "AUTHORIZED_PILOT_GEOMETRY_BACKFILL",
                    "lookup_enabled": False,
                },
                {
                    "phase": 3,
                    "name":
                        "READ_ONLY_PILOT_ENDPOINT_SHADOW",
                    "lookup_enabled": False,
                },
                {
                    "phase": 4,
                    "name":
                        "ADMIN_ONLY_PILOT_ENABLEMENT",
                    "lookup_enabled":
                        "SEPARATE_AUTHORIZATION_REQUIRED",
                },
                {
                    "phase": 5,
                    "name":
                        "NATIONAL_ROLLOUT",
                    "lookup_enabled":
                        "OUT_OF_SCOPE",
                },
            ],
        },
        "backfill_contract": {
            "authorization_required": True,
            "idempotent": True,
            "restartable": True,
            "single_writer": True,
            "bounded_transaction_rows": 25000,
            "maximum_transaction_rows": 50000,
            "required_identity_checks": [
                "runtime_set_id",
                "runtime_feature_id",
                "source_feature_id",
                "source_feature_index",
                "village_id",
                "village_lgd_code",
                "normalized source checksum",
                "canonical normalized geometry hash",
            ],
            "required_reconciliation": [
                "authorized row total",
                "native geometry row total",
                "valid geometry total",
                "non-empty geometry total",
                "SRID 4326 total",
                "runtime crosswalk linkage total",
                "zero ambiguous active village identities",
            ],
        },
        "observability": {
            "metrics": [
                "lookup request count",
                "matched request count",
                "unmatched request count",
                "ambiguous request count",
                "lookup error count",
                "query duration histogram",
                "active indexed geometry count",
            ],
            "audit": {
                "write_per_lookup": False,
                "log_sensitive_coordinates": False,
                "record_aggregate_metrics_only": True,
            },
        },
        "rollback_and_kill_switch": {
            "first_action":
                "Set feature flag false",
            "second_action":
                "Confirm endpoint returns disabled response",
            "data_action":
                "Preserve native geometry and audit evidence",
            "runtime_action":
                "Do not deactivate runtime rows automatically",
            "schema_rollback":
                "Separate reviewed migration only",
            "android_action":
                "No Android rollback required because Android remains unchanged",
        },
        "acceptance_gates": {
            "migration_reviewed": False,
            "backfill_authorized": False,
            "backfill_reconciled": False,
            "gist_index_present": False,
            "query_plan_uses_spatial_index": False,
            "pilot_endpoint_implemented": False,
            "pilot_endpoint_regression_passed": False,
            "ambiguity_policy_regression_passed": False,
            "feature_flag_default_off_verified": False,
            "load_test_passed": False,
            "rollback_drill_passed": False,
            "security_review_passed": False,
            "production_enablement_authorized": False,
        },
        "readiness": {
            "ready_for_schema_migration_proposal":
                all(reuse_evidence.values()),
            "ready_for_geometry_backfill": False,
            "ready_for_endpoint_implementation": False,
            "ready_for_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
            "requires_separate_authorization_for_each_phase":
                True,
        },
        "guardrails": {
            "database_writes_attempted": False,
            "migration_applied": False,
            "runtime_tables_written": False,
            "runtime_geometry_backfilled": False,
            "lookup_endpoint_added": False,
            "lookup_api_enabled": False,
            "project_matches_written": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "source_features_changed": False,
            "source_files_changed": False,
            "android_behavior_changed": False,
        },
    }

    options.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    options.output.write_text(
        json.dumps(
            design,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(
        design,
        indent=2,
        sort_keys=True,
    ))

    return 0 if design["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
