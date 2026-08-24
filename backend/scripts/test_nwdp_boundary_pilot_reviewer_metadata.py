#!/usr/bin/env python3
"""Regression for guarded NWDP pilot reviewer-metadata checkpoint."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
REVIEW_SCRIPT = ROOT / "backend" / "scripts" / "review_nwdp_boundary_pilot_candidates.py"
PROMOTION_SCRIPT = ROOT / "backend" / "scripts" / "promote_nwdp_boundary_runtime.py"
REVIEW_OUTPUT = Path("/tmp/nwdp-boundary-pilot-reviewer-metadata-regression.json")
PROMOTION_OUTPUT = Path("/tmp/nwdp-boundary-runtime-promotion-after-pilot-review-regression.json")


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


def runtime_counts() -> dict[str, int]:
    engine = create_engine(db_url_from_settings())
    tables = [
        "geography_boundary_runtime_sets",
        "geography_boundary_runtime_features",
        "geography_boundary_runtime_crosswalks",
        "geography_boundary_runtime_promotion_events",
    ]
    with engine.connect() as conn:
        return {table: int(conn.execute(text(f"select count(*) from {table}")).scalar() or 0) for table in tables}


def pilot_review_counts() -> dict:
    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        return dict(conn.execute(text("""
            select
              count(*) as pilot_count,
              sum(case when c.review_status = 'APPROVED_FOR_PROMOTION' then 1 else 0 end) as approved_count,
              sum(case when c.reviewer_decision = 'ACCEPT_DIRECT_CODE_MATCH' then 1 else 0 end) as accepted_direct_count,
              sum(case when c.is_active = false then 1 else 0 end) as inactive_count,
              sum(case when c.promotion_status = 'NOT_PROMOTED' then 1 else 0 end) as not_promoted_count,
              sum(case when f.geometry_validation_status = 'VALIDATED' then 1 else 0 end) as validated_count
            from geography_boundary_crosswalk_candidates c
            join geography_boundary_source_features f on f.id = c.source_feature_id
            join geography_boundary_import_batches b on b.id = c.import_batch_id
            where b.state_or_ut = 'Karnataka'
              and b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.proposed_scope in ('village', 'village_review')
              and f.metadata ? 'pilot_geometry_materialized_at'
        """)).mappings().one())


def run_json(script: Path, output: Path, *args: str) -> tuple[int, dict]:
    if output.exists():
        output.unlink()
    proc = subprocess.run(
        [str(PYTHON), str(script), "--output", str(output), *args],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert_pass(f"{script.name} wrote output", output.exists(), proc.stdout)
    return proc.returncode, json.loads(output.read_text(encoding="utf-8"))


def main() -> None:
    zero_runtime = {
        "geography_boundary_runtime_sets": 0,
        "geography_boundary_runtime_features": 0,
        "geography_boundary_runtime_crosswalks": 0,
        "geography_boundary_runtime_promotion_events": 0,
    }

    before_runtime = runtime_counts()
    assert_pass("Runtime tables start empty", before_runtime == zero_runtime, before_runtime)

    code, review = run_json(REVIEW_SCRIPT, REVIEW_OUTPUT, "--apply", "--limit", "10")
    assert_pass("Reviewer metadata apply exits zero", code == 0, review)
    assert_pass("Reviewer metadata schema version is stable", review.get("schema_version") == "nwdp_boundary_pilot_reviewer_metadata.v1", review)
    assert_pass("Reviewer metadata apply is healthy", review.get("healthy") is True, review)
    assert_pass("Reviewer metadata updates 10 rows", review.get("staging_review_rows_updated") == 10, review)
    assert_pass("Reviewer metadata writes no runtime tables", review.get("runtime_tables_written") is False, review)
    assert_pass("Reviewer metadata keeps runtime matching disabled", review.get("runtime_spatial_matching_changed") is False, review)
    assert_pass("Reviewer metadata keeps Android unchanged", review.get("android_behavior_changed") is False, review)

    counts = pilot_review_counts()
    assert_pass("Ten pilot rows are approved for promotion metadata only", counts == {
        "pilot_count": 10,
        "approved_count": 10,
        "accepted_direct_count": 10,
        "inactive_count": 10,
        "not_promoted_count": 10,
        "validated_count": 10,
    }, counts)

    after_review_runtime = runtime_counts()
    assert_pass("Runtime tables remain empty after reviewer metadata", after_review_runtime == zero_runtime, after_review_runtime)

    code, promotion = run_json(PROMOTION_SCRIPT, PROMOTION_OUTPUT)
    assert_pass("Runtime promotion dry-run exits zero", code == 0, promotion)
    assert_pass("Runtime promotion dry-run attempts no DB writes", promotion.get("db_writes_attempted") is False, promotion)
    assert_pass("Runtime promotion dry-run writes no runtime tables", promotion.get("runtime_tables_written") is False, promotion)
    assert_pass("Runtime promotion dry-run has zero effective runtime rows", promotion.get("runtime_rows_effective") == 0, promotion)

    plan = promotion.get("plan") or {}
    assert_pass("Runtime promotion dry-run sees 10 promotable pilot candidates", plan.get("promotable_candidate_count") == 10, plan)
    assert_pass("Runtime promotion dry-run excludes remaining candidates", plan.get("excluded_candidate_count") == 29779, plan)
    assert_pass("Runtime promotion dry-run plans one runtime set", plan.get("planned_runtime_set_insert_count") == 1, plan)
    assert_pass("Runtime promotion dry-run plans 10 runtime features", plan.get("planned_runtime_feature_insert_count") == 10, plan)
    assert_pass("Runtime promotion dry-run plans 10 runtime crosswalks", plan.get("planned_runtime_crosswalk_insert_count") == 10, plan)
    assert_pass("Runtime promotion dry-run does not allow runtime write yet", promotion["readiness"]["ready_for_runtime_table_write"] is False, promotion["readiness"])
    assert_pass("Runtime promotion dry-run keeps runtime matching disabled", promotion["readiness"]["ready_for_runtime_spatial_matching"] is False, promotion["readiness"])
    assert_pass("Runtime promotion dry-run keeps Android unchanged", promotion["readiness"]["android_behavior_changed"] is False, promotion["readiness"])

    after_promotion_runtime = runtime_counts()
    assert_pass("Runtime tables remain empty after promotion dry-run", after_promotion_runtime == zero_runtime, after_promotion_runtime)

    print("=" * 72)
    print("NWDP BOUNDARY PILOT REVIEWER METADATA REGRESSION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
