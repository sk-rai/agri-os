#!/usr/bin/env python3
"""Read-only schema guard for NWDP boundary review staging migration."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_MIGRATION = Path("backend/alembic/versions/054_add_nwdp_boundary_review_staging.py")
DEFAULT_OUTPUT = Path("/tmp/nwdp-boundary-staging-schema-guard.json")

REQUIRED_TOKENS = {
    "batch_table": "geography_boundary_import_batches",
    "source_feature_table": "geography_boundary_source_features",
    "candidate_table": "geography_boundary_crosswalk_candidates",
    "candidate_inactive_check": "ck_geography_boundary_candidates_inactive_by_default",
    "batch_status": '"status"',
    "review_status": '"review_status"',
    "promotion_status": '"promotion_status"',
    "source_feature_index": '"source_feature_index"',
    "source_geometry_hash": '"source_geometry_hash"',
    "transformed_centroid": '"transformed_centroid"',
    "proposed_scope": '"proposed_scope"',
    "proposed_village_id": '"proposed_village_id"',
    "source_codes": '"source_codes"',
    "source_names": '"source_names"',
    "match_evidence": '"match_evidence"',
    "reviewer_decision": '"reviewer_decision"',
}

FORBIDDEN_TOKENS = {
    "candidate_active_default_true": 'sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"))',
    "runtime_lookup_table_create": 'op.create_table("geography_boundary_runtime',
    "runtime_lookup_index_create": 'op.create_index("idx_geography_boundary_runtime',
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify NWDP boundary staging migration guardrails.")
    parser.add_argument("--migration", default=str(DEFAULT_MIGRATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    migration_path = Path(args.migration)
    output_path = Path(args.output)

    if not migration_path.exists():
        result = {
            "schema_version": "nwdp_boundary_staging_schema_guard.v1",
            "healthy": False,
            "error": "MIGRATION_NOT_FOUND",
            "path": str(migration_path),
        }
    else:
        text = migration_path.read_text(encoding="utf-8")

        token_checks = {
            name: token in text
            for name, token in REQUIRED_TOKENS.items()
        }
        forbidden_checks = {
            name: token in text
            for name, token in FORBIDDEN_TOKENS.items()
        }

        result = {
            "schema_version": "nwdp_boundary_staging_schema_guard.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "healthy": all(token_checks.values()) and not any(forbidden_checks.values()),
            "migration": str(migration_path),
            "required_token_checks": token_checks,
            "forbidden_token_checks": forbidden_checks,
            "readiness": {
                "safe_read_only": True,
                "db_writes_attempted": False,
                "migration_applied": False,
                "ready_for_schema_review": all(token_checks.values()) and not any(forbidden_checks.values()),
                "ready_for_runtime_spatial_matching": False,
            },
            "claim_boundary": "Schema guard inspects migration text only. It does not run Alembic, write DB rows, import geometry, or enable runtime boundary lookup.",
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
