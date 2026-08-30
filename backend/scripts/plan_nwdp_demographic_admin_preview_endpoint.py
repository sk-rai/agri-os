#!/usr/bin/env python3
"""Plan disabled/read-only admin preview endpoint for NWDP demographic profiles."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def build_plan() -> dict:
    return {
        "schema_version": "nwdp_demographic_admin_preview_endpoint_plan.v1",
        "mode": "READ_ONLY_DISABLED_ADMIN_PREVIEW_ENDPOINT_PLAN",
        "healthy": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_endpoint": "GET /api/v1/master-data/geography/nwdp-demographic-profiles/preview",
        "target_table": "geography_village_demographic_profiles",
        "status": "planned_disabled_until_profile_import",
        "claim_boundary": (
            "Endpoint plan only. It does not implement runtime lookup, does not insert profile rows, "
            "does not promote profiles, does not expose Android behavior, and does not claim official Census import."
        ),
        "intended_behavior": {
            "method": "GET",
            "auth_scope": "admin/read",
            "writes_db": False,
            "default_response_when_empty": {
                "schema_version": "nwdp_demographic_profiles_admin_preview.v1",
                "healthy": True,
                "enabled": False,
                "reason": "NO_DEMOGRAPHIC_PROFILE_ROWS_IMPORTED",
                "profile_row_count": 0,
                "active_profile_row_count": 0,
                "promoted_profile_row_count": 0,
                "ready_for_profile_apply": False,
                "ready_for_android_behavior_change": False,
            },
            "future_preview_fields": [
                "state_or_ut",
                "district",
                "village_name",
                "village_lgd_code",
                "source_system",
                "source_version",
                "source_vlcode",
                "total_population",
                "total_households",
                "rural_urban",
                "review_status",
                "promotion_status",
                "is_active",
            ],
        },
        "implementation_notes": [
            "Add route under backend/app/modules/master_data/api/geography.py or a small included geography admin router.",
            "Read counts from geography_village_demographic_profiles only.",
            "Return enabled=false while profile_row_count is zero.",
            "Do not join large source payloads by default.",
            "Do not expose this to Android runtime endpoints.",
            "Do not claim official Census PCA/DCHB import.",
        ],
        "guardrails": {
            "endpoint_implemented": False,
            "db_writes_attempted": False,
            "demographic_profile_rows_written": False,
            "profiles_promoted": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "official_census_claimed_imported": False,
        },
        "readiness": {
            "ready_for_endpoint_implementation": True,
            "ready_for_profile_import_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/nwdp-demographic-admin-preview-endpoint-plan.json"))
    args = parser.parse_args()

    plan = build_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "healthy": plan["healthy"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
