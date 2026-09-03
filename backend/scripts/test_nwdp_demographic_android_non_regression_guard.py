#!/usr/bin/env python3
"""Guard that promoted NWDP demographic profiles do not change Android behavior yet."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.apply_nwdp_demographic_profile_import import SOURCE_SYSTEM, SOURCE_VERSION, load_settings_url  # noqa: E402


ANDROID_ROOT = REPO_ROOT / "app/src/main/java"
FARMER_API = BACKEND_ROOT / "app/modules/farmer/api.py"

FORBIDDEN_ANDROID_RUNTIME_STRINGS = [
    "nwdp-demographic-profiles",
    "nwdp_demographic",
    "demographic_profile",
    "total_population",
    "total_households",
    "source_vlcode",
]

FORBIDDEN_FARMER_PAYLOAD_STRINGS = [
    "nwdp_demographic",
    "demographic_profile",
    "total_population",
    "total_households",
    "source_vlcode",
    "source_system",
    "source_version",
    "promoted_profile_row_count",
]


def check(condition, label, detail=None):
    if condition:
        print(f"PASS {label}")
        if detail is not None:
            print(json.dumps(detail, indent=2, sort_keys=True))
        return
    print(f"FAIL {label}")
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True))
    raise AssertionError(label)


def profile_counts():
    engine = create_engine(load_settings_url())
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                  COUNT(*)::bigint AS profile_row_count,
                  COUNT(*) FILTER (
                    WHERE review_status = 'APPROVED_FOR_PROMOTION'
                  )::bigint AS approved_for_promotion_count,
                  COUNT(*) FILTER (
                    WHERE is_active = true
                      AND promotion_status = 'PROMOTED'
                  )::bigint AS active_promoted_profile_row_count,
                  COUNT(*) FILTER (
                    WHERE review_status = 'APPROVED_FOR_PROMOTION'
                      AND promotion_status = 'NOT_PROMOTED'
                      AND is_active = false
                  )::bigint AS remaining_eligible_profile_row_count
                FROM geography_village_demographic_profiles
                WHERE source_system = :source_system
                  AND source_version = :source_version
                """
            ),
            {"source_system": SOURCE_SYSTEM, "source_version": SOURCE_VERSION},
        ).mappings().one()
    return dict(row)


def farmer_payload_source():
    text_body = FARMER_API.read_text(encoding="utf-8")
    start = text_body.index("def _farmer_payload")
    end = text_body.index("def _parcel_payload")
    return text_body[start:end].lower()


def android_runtime_hits():
    hits = []
    if not ANDROID_ROOT.exists():
        return hits
    for path in ANDROID_ROOT.rglob("*.kt"):
        text_body = path.read_text(encoding="utf-8", errors="ignore").lower()
        for needle in FORBIDDEN_ANDROID_RUNTIME_STRINGS:
            if needle in text_body:
                hits.append({"file": str(path.relative_to(REPO_ROOT)), "needle": needle})
    return hits


def main():
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ANDROID NON-REGRESSION GUARD")
    print("=" * 72)

    counts = profile_counts()
    check(counts["profile_row_count"] == 453036, "NWDP demographic profile total is stable", counts)
    check(counts["approved_for_promotion_count"] == 680, "Six hundred eighty profiles remain approved after rollout checkpoints", counts)
    check(counts["active_promoted_profile_row_count"] == 680, "Six hundred eighty profiles are promoted and active for web/admin verification", counts)
    check(counts["remaining_eligible_profile_row_count"] == 0, "No approved inactive profiles remain eligible after promotion checkpoint", counts)

    payload = farmer_payload_source()
    farmer_hits = [needle for needle in FORBIDDEN_FARMER_PAYLOAD_STRINGS if needle in payload]
    check(not farmer_hits, "Android-facing farmer payload exposes no NWDP demographic profile fields", farmer_hits)

    hits = android_runtime_hits()
    check(not hits, "Android app has no NWDP demographic runtime lookup wiring yet", hits)

    result = {
        "schema_version": "nwdp_demographic_android_non_regression_guard.v1",
        "healthy": True,
        "counts": counts,
        "guardrails": {
            "android_behavior_changed": False,
            "android_runtime_lookup_enabled": False,
            "frontend_web_admin_preview_enabled": True,
            "promoted_demographic_profiles_available_for_admin_web": True,
            "runtime_lookup_enabled": False,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ANDROID NON-REGRESSION GUARD PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
