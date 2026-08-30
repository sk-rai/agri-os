#!/usr/bin/env python3
"""Regression for NWDP demographic enrichment schema-only Alembic migration file."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend/alembic/versions/057_add_village_demographic_profiles.py"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1600])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ENRICHMENT SCHEMA MIGRATION FILE REGRESSION")
    print("=" * 72)

    check(MIGRATION.exists(), "Migration file exists", {"path": str(MIGRATION)})
    text = MIGRATION.read_text(encoding="utf-8")

    check('revision = "057"' in text, "Revision id is 057")
    check('down_revision = "056"' in text, "Down revision is 056")
    check('"geography_village_demographic_profiles"' in text, "Target table is created")
    check('sa.ForeignKey("geography_villages.id")' in text, "Village FK is present")
    check('"source_system"' in text, "Source system column present")
    check('"source_version"' in text, "Source version column present")
    check('"source_feature_id"' in text, "Source feature id column present")
    check('"source_vlcode"' in text, "Source vlcode column present")
    check('"total_population"' in text, "Total population column present")
    check('"total_households"' in text, "Total households column present")
    check('"net_area_sown"' in text, "Land-use column present")
    check('"handpump_status"' in text, "Amenity status column present")
    check("postgresql.JSONB" in text, "JSONB source/evidence columns present")
    check("source_properties" in text and "match_evidence" in text, "Source properties and match evidence are preserved")
    check('"is_active"' in text and 'sa.text("false")' in text, "Profiles default inactive")
    check('"promotion_status"' in text and "NOT_PROMOTED" in text, "Profiles default not promoted")
    check("uq_geography_village_demographic_profiles_source_feature" in text, "Source-feature uniqueness index present")
    check("uq_geography_village_demographic_profiles_active_promoted" in text, "Active promoted uniqueness index present")

    forbidden_fragments = [
        "op.execute(",
        "bulk_insert",
        "insert into geography_village_demographic_profiles",
        "update geography_villages",
        "android_behavior",
        "lookup_api",
    ]
    for fragment in forbidden_fragments:
        check(fragment not in text, f"Migration avoids forbidden fragment: {fragment}")

    check("op.drop_table" in text, "Downgrade drops table")

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ENRICHMENT SCHEMA MIGRATION FILE REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
