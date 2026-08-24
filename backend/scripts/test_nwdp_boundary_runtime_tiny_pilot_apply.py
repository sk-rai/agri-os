#!/usr/bin/env python3
"""Regression for NWDP boundary tiny-pilot runtime apply checkpoint.

This regression assumes the local tiny pilot runtime apply checkpoint has already
been executed. It verifies the runtime row shape, inactive guardrails, staging
candidate guardrails, and repeat-apply preflight block.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
PROMOTION_SCRIPT = ROOT / "backend" / "scripts" / "promote_nwdp_boundary_runtime.py"
REPEAT_OUTPUT = Path("/tmp/nwdp-boundary-runtime-tiny-pilot-repeat-blocked-regression.json")


def db_url_from_settings() -> str:
    backend = ROOT / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from app.core.config import settings

    value = (
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )
    return str(value or "postgresql+psycopg2://agri_os:agri_os_dev@localhost:5432/agri_os")


def assert_pass(name: str, condition: bool, payload=None) -> None:
    if not condition:
        print(f"FAIL {name}")
        if payload is not None:
            print(json.dumps(payload, indent=2, default=str)[:2400])
        raise SystemExit(1)
    print(f"PASS {name}")
    if payload is not None:
        print("    ", json.dumps(payload, indent=2, default=str)[:1200])


def db_snapshot() -> dict:
    engine = create_engine(db_url_from_settings())
    runtime_tables = [
        "geography_boundary_runtime_sets",
        "geography_boundary_runtime_features",
        "geography_boundary_runtime_crosswalks",
        "geography_boundary_runtime_promotion_events",
    ]

    with engine.connect() as conn:
        runtime_counts = {
            table: int(conn.execute(text(f"select count(*) from {table}")).scalar() or 0)
            for table in runtime_tables
        }
        runtime_active_counts = {
            table: int(conn.execute(text(f"select count(*) from {table} where is_active = true")).scalar() or 0)
            for table in runtime_tables
        }
        runtime_set_status = [dict(row) for row in conn.execute(text("""
            select status, activation_status, is_active, count(*) as count
            from geography_boundary_runtime_sets
            group by status, activation_status, is_active
            order by status, activation_status, is_active
        """)).mappings().all()]
        promotion_event_status = [dict(row) for row in conn.execute(text("""
            select promotion_mode, promotion_status, is_active, candidate_count, runtime_feature_count, runtime_crosswalk_count, count(*) as count
            from geography_boundary_runtime_promotion_events
            group by promotion_mode, promotion_status, is_active, candidate_count, runtime_feature_count, runtime_crosswalk_count
            order by promotion_mode, promotion_status, is_active
        """)).mappings().all()]
        candidate_guardrails = dict(conn.execute(text("""
            select
              count(*) as pilot_count,
              sum(case when c.is_active = false then 1 else 0 end) as inactive_count,
              sum(case when c.promotion_status = 'NOT_PROMOTED' then 1 else 0 end) as not_promoted_count,
              sum(case when c.review_status = 'APPROVED_FOR_PROMOTION' then 1 else 0 end) as approved_count,
              sum(case when c.reviewer_decision = 'ACCEPT_DIRECT_CODE_MATCH' then 1 else 0 end) as accepted_direct_count
            from geography_boundary_runtime_crosswalks rw
            join geography_boundary_crosswalk_candidates c on c.id = rw.source_candidate_id
        """)).mappings().one())
        runtime_feature_guardrails = dict(conn.execute(text("""
            select
              count(*) as feature_count,
              sum(case when geometry_validation_status = 'VALIDATED' then 1 else 0 end) as validated_count,
              sum(case when geometry_hash is not null then 1 else 0 end) as hash_count,
              sum(case when bbox_wgs84 <> '[]'::jsonb then 1 else 0 end) as bbox_count,
              sum(case when centroid_wgs84 <> '{}'::jsonb then 1 else 0 end) as centroid_count
            from geography_boundary_runtime_features
        """)).mappings().one())

    return {
        "runtime_counts": runtime_counts,
        "runtime_active_counts": runtime_active_counts,
        "runtime_set_status": runtime_set_status,
        "promotion_event_status": promotion_event_status,
        "candidate_guardrails": candidate_guardrails,
        "runtime_feature_guardrails": runtime_feature_guardrails,
    }


def run_repeat_apply() -> tuple[int, dict]:
    if REPEAT_OUTPUT.exists():
        REPEAT_OUTPUT.unlink()
    proc = subprocess.run(
        [
            str(PYTHON),
            str(PROMOTION_SCRIPT),
            "--apply",
            "--allow-tiny-pilot-runtime-write",
            "--output",
            str(REPEAT_OUTPUT),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert_pass("Repeat apply wrote output", REPEAT_OUTPUT.exists(), proc.stdout)
    return proc.returncode, json.loads(REPEAT_OUTPUT.read_text(encoding="utf-8"))


def main() -> None:
    expected_counts = {
        "geography_boundary_runtime_sets": 1,
        "geography_boundary_runtime_features": 10,
        "geography_boundary_runtime_crosswalks": 10,
        "geography_boundary_runtime_promotion_events": 1,
    }

    snapshot = db_snapshot()
    assert_pass("Runtime tiny pilot row shape is stable", snapshot["runtime_counts"] == expected_counts, snapshot)
    assert_pass("Runtime rows are all inactive", all(value == 0 for value in snapshot["runtime_active_counts"].values()), snapshot["runtime_active_counts"])
    assert_pass("Runtime set remains inactive", snapshot["runtime_set_status"] == [{
        "status": "PILOT_IMPORTED_INACTIVE",
        "activation_status": "INACTIVE",
        "is_active": False,
        "count": 1,
    }], snapshot["runtime_set_status"])
    assert_pass("Promotion event records applied inactive pilot", snapshot["promotion_event_status"] == [{
        "promotion_mode": "TINY_PILOT_REVIEWED_BATCH",
        "promotion_status": "APPLIED",
        "is_active": False,
        "candidate_count": 10,
        "runtime_feature_count": 10,
        "runtime_crosswalk_count": 10,
        "count": 1,
    }], snapshot["promotion_event_status"])
    assert_pass("Staging candidates remain inactive and unpromoted", snapshot["candidate_guardrails"] == {
        "pilot_count": 10,
        "inactive_count": 10,
        "not_promoted_count": 10,
        "approved_count": 10,
        "accepted_direct_count": 10,
    }, snapshot["candidate_guardrails"])
    assert_pass("Runtime feature metadata is present", snapshot["runtime_feature_guardrails"] == {
        "feature_count": 10,
        "validated_count": 10,
        "hash_count": 10,
        "bbox_count": 10,
        "centroid_count": 10,
    }, snapshot["runtime_feature_guardrails"])

    code, repeat = run_repeat_apply()
    assert_pass("Repeat apply exits non-zero", code == 1, repeat)
    assert_pass("Repeat apply is blocked by non-empty runtime tables", repeat.get("error") == "RUNTIME_TABLES_NOT_EMPTY_TINY_PILOT_APPLY_REQUIRES_EMPTY_RUNTIME_TABLES", repeat)
    assert_pass("Repeat apply attempts no DB writes", repeat.get("db_writes_attempted") is False, repeat)
    assert_pass("Repeat apply writes no runtime rows", repeat.get("runtime_rows_effective") == 0, repeat)
    assert_pass("Repeat apply reports existing runtime counts", (repeat.get("target_table_check") or {}).get("counts") == expected_counts, repeat.get("target_table_check"))

    print("=" * 72)
    print("NWDP BOUNDARY RUNTIME TINY PILOT APPLY REGRESSION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
