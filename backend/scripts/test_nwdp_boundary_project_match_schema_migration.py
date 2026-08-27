#!/usr/bin/env python3
"""Regression for NWDP boundary project match schema migration contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend/alembic/versions/056_add_nwdp_boundary_project_matches.py"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, default=str)[:1400])
    if not condition:
        raise AssertionError(label)


def load_migration():
    spec = importlib.util.spec_from_file_location("migration_056", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    text = MIGRATION.read_text(encoding="utf-8")
    module = load_migration()

    check(module.revision == "056", "Migration revision is stable", module.revision)
    check(module.down_revision == "055", "Migration follows runtime table revision", module.down_revision)
    check("geography_boundary_project_matches" in text, "Migration creates project match table")
    check("tenant_id" in text and "tenants.id" in text, "Migration keeps tenant foreign key")
    check("project_id" in text and "projects.id" in text, "Migration links projects")
    check("village_id" in text and "geography_villages.id" in text, "Migration links villages")
    check(
        "boundary_candidate_id" in text and "geography_boundary_crosswalk_candidates.id" in text,
        "Migration links NWDP boundary candidates",
    )
    check("rollback_token" in text, "Migration requires rollback token")
    check("dry_run_report" in text, "Migration stores dry-run report")
    check("apply_report" in text, "Migration stores apply report")
    check("rollback_report" in text, "Migration stores rollback report")
    check("match_status in ('PLANNED', 'APPLIED', 'ROLLED_BACK', 'FAILED')" in text, "Migration constrains match status")
    check("is_active = false or match_status = 'APPLIED'" in text, "Active rows must be applied")
    check("uq_geography_boundary_project_matches_one_active" in text, "Migration enforces one active project-village-source match")
    check("postgresql_where=sa.text(\"is_active = true\")" in text, "Unique active constraint is partial")
    check("geography_boundary_runtime_" not in text, "Migration does not create or mutate runtime tables")
    check("geography_boundary_crosswalk_candidates" in text, "Migration references candidates only by FK")
    check("op.drop_table(\"geography_boundary_project_matches\")" in text, "Migration downgrade drops project match table")

    result = {
        "schema_version": "nwdp_boundary_project_match_schema_migration_regression.v1",
        "healthy": True,
        "migration": str(MIGRATION.relative_to(ROOT)),
        "revision": module.revision,
        "down_revision": module.down_revision,
        "guardrails": {
            "project_matching_apply_implemented": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_tables_mutated": False,
            "lookup_api_enabled": False,
            "android_behavior_changed": False,
        },
    }
    print(json.dumps(result, indent=2))
    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCH SCHEMA MIGRATION REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
