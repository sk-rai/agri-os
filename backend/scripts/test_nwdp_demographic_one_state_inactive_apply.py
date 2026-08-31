#!/usr/bin/env python3
"""Regression for guarded one-state inactive NWDP demographic profile apply."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend/scripts/apply_nwdp_demographic_profile_import.py"
OUTPUT = Path("/tmp/nwdp-demographic-one-state-inactive-apply-regression.json")
STATE = "Andaman & Nicobar Island"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
SOURCE_VERSION = "20260824T110250Z"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:1800])
    if not condition:
        raise AssertionError(label)


def db_query(sql: str, params: dict | None = None):
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        return db.execute(text(sql), params or {}).mappings().all()


def profile_counts() -> dict:
    rows = db_query("""
        select
          count(*) as profile_row_count,
          count(*) filter (where is_active = true) as active_profile_row_count,
          count(*) filter (where promotion_status = 'PROMOTED') as promoted_profile_row_count
        from geography_village_demographic_profiles
    """)
    return dict(rows[0])


def cleanup_inserted(source_feature_ids: list[str]) -> None:
    if not source_feature_ids:
        return

    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        db.execute(
            text("""
                delete from geography_village_demographic_profiles
                where source_system = :source_system
                  and source_version = :source_version
                  and source_feature_id = any(cast(:source_feature_ids as uuid[]))
            """),
            {
                "source_system": SOURCE_SYSTEM,
                "source_version": SOURCE_VERSION,
                "source_feature_ids": source_feature_ids,
            },
        )
        db.commit()


def run_apply() -> dict:
    if OUTPUT.exists():
        OUTPUT.unlink()

    proc = subprocess.run(
        [
            str(PYTHON),
            str(SCRIPT),
            "--state-or-ut",
            STATE,
            "--apply",
            "--limit",
            "5",
            "--max-rows",
            "10",
            "--output",
            str(OUTPUT),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    check(OUTPUT.exists(), "Apply writes audit output", proc.stdout)
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    check(proc.returncode == 0, "Guarded one-state apply exits zero", data)
    return data


def main() -> int:
    print("=" * 72)
    print("NWDP DEMOGRAPHIC ONE-STATE INACTIVE APPLY REGRESSION")
    print("=" * 72)

    before = profile_counts()
    inserted_ids: list[str] = []

    try:
        first = run_apply()
        check(first["healthy"] is True, "First apply is healthy", first)
        check(first["state_or_ut"] == STATE, "Apply echoes state scope", first)
        check(first["apply"] is True, "Apply flag is recorded", first)
        check(first["apply_result"]["planned_insert_count"] == 5, "First apply plans five rows", first["apply_result"])
        check(first["apply_result"]["inserted_count"] in (0, 5), "First apply inserts or idempotently skips five rows", first["apply_result"])
        check(first["apply_result"]["skipped_existing_count"] in (0, 5), "First apply skip count is expected", first["apply_result"])
        check(first["apply_result"]["inserted_count"] + first["apply_result"]["skipped_existing_count"] == 5, "First apply accounts for all five rows", first["apply_result"])
        check(len(first["apply_result"]["state_district_summary"]) > 0, "Apply reports state/district summary", first["apply_result"])
        inserted_ids = first["apply_result"]["sample_inserted_source_feature_ids"]
        check(len(inserted_ids) == first["apply_result"]["inserted_count"], "Apply records newly inserted source feature ids", inserted_ids)

        if inserted_ids:
            rows = db_query(
            """
            select
              count(*) as inserted_count,
              count(*) filter (where review_status = 'AUTO_CANDIDATE') as auto_candidate_count,
              count(*) filter (where promotion_status = 'NOT_PROMOTED') as not_promoted_count,
              count(*) filter (where is_active = false) as inactive_count,
              count(*) filter (where source_state_name = :state) as scoped_state_count
            from geography_village_demographic_profiles
            where source_system = :source_system
              and source_version = :source_version
              and source_feature_id = any(cast(:source_feature_ids as uuid[]))
            """,
            {
                "state": STATE,
                "source_system": SOURCE_SYSTEM,
                "source_version": SOURCE_VERSION,
                "source_feature_ids": inserted_ids,
            },
        )
            db_counts = dict(rows[0])
            check(db_counts["inserted_count"] == len(inserted_ids), "Inserted rows are present in DB", db_counts)
            check(db_counts["auto_candidate_count"] == len(inserted_ids), "Inserted rows are auto candidates", db_counts)
            check(db_counts["not_promoted_count"] == len(inserted_ids), "Inserted rows are not promoted", db_counts)
            check(db_counts["inactive_count"] == len(inserted_ids), "Inserted rows are inactive", db_counts)
            check(db_counts["scoped_state_count"] == len(inserted_ids), "Inserted rows stay in scoped state", db_counts)

        second = run_apply()
        check(second["apply_result"]["planned_insert_count"] == 5, "Second apply plans same five rows", second["apply_result"])
        check(second["apply_result"]["inserted_count"] == 0, "Second apply is idempotent", second["apply_result"])
        check(second["apply_result"]["skipped_existing_count"] == 5, "Second apply skips existing rows", second["apply_result"])

    finally:
        cleanup_inserted(inserted_ids)

    after = profile_counts()
    check(after == before, "Regression cleaned up inserted profile rows", {"before": before, "after": after})

    print("=" * 72)
    print("NWDP DEMOGRAPHIC ONE-STATE INACTIVE APPLY REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
