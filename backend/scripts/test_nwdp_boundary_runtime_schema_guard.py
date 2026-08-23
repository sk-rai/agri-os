#!/usr/bin/env python3
"""Schema guard for NWDP boundary runtime table migration.

This guard inspects migration text only. It does not run Alembic, create tables,
write runtime rows, promote candidates, or enable point-in-polygon lookup.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend" / "alembic" / "versions" / "055_add_nwdp_boundary_runtime_tables.py"

REQUIRED_TOKENS = {
    "runtime_set_table": "geography_boundary_runtime_sets",
    "runtime_feature_table": "geography_boundary_runtime_features",
    "runtime_crosswalk_table": "geography_boundary_runtime_crosswalks",
    "promotion_event_table": "geography_boundary_runtime_promotion_events",
    "runtime_set_inactive_default": "server_default=sa.text(\"false\")",
    "activation_status": "activation_status",
    "one_active_index": "uq_geography_boundary_runtime_sets_one_active",
    "promotion_event_fk": "fk_geography_boundary_runtime_crosswalks_promotion_event",
}

FORBIDDEN_TOKENS = {
    "runtime_lookup_endpoint": "boundary-runtime/lookup",
    "android_feature_flag_enable": "boundary_runtime_android_enabled = true",
    "runtime_set_active_default": "server_default=sa.text(\"true\")",
    "candidate_active_update": "update geography_boundary_crosswalk_candidates set is_active = true",
    "candidate_promoted_update": "promotion_status = 'PROMOTED'",
}


def main() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    required = {name: token in text for name, token in REQUIRED_TOKENS.items()}
    forbidden = {name: token in text for name, token in FORBIDDEN_TOKENS.items()}
    healthy = all(required.values()) and not any(forbidden.values())

    report = {
        "schema_version": "nwdp_boundary_runtime_schema_guard.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "migration": str(MIGRATION.relative_to(ROOT)),
        "claim_boundary": "Runtime schema guard inspects migration text only. It does not run Alembic, write runtime rows, promote candidates, or enable Android/runtime lookup.",
        "required_token_checks": required,
        "forbidden_token_checks": forbidden,
        "readiness": {
            "ready_for_schema_review": healthy,
            "db_writes_attempted": False,
            "migration_applied": False,
            "ready_for_runtime_spatial_matching": False,
            "android_behavior_changed": False,
            "safe_read_only": True,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
