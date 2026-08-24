#!/usr/bin/env python3
"""Regression for guarded NWDP pilot staging geometry materializer."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv" / "bin" / "python"
SCRIPT = ROOT / "backend" / "scripts" / "materialize_nwdp_boundary_pilot_geometry.py"
OUTPUT = Path("/tmp/nwdp-boundary-pilot-geometry-materializer-regression.json")


def db_url_from_settings() -> str:
    import sys
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
            print(json.dumps(payload, indent=2, default=str)[:2000])
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


def staged_counts() -> dict:
    engine = create_engine(db_url_from_settings())
    with engine.connect() as conn:
        return dict(conn.execute(text("""
            select
              count(*) as pilot_count,
              sum(case when f.source_geometry_hash is not null then 1 else 0 end) as hash_count,
              sum(case when f.transformed_bbox <> '[]'::jsonb then 1 else 0 end) as bbox_count,
              sum(case when f.transformed_centroid <> '{}'::jsonb then 1 else 0 end) as centroid_count,
              sum(case when f.geometry_validation_status = 'VALIDATED' then 1 else 0 end) as validated_count
            from geography_boundary_crosswalk_candidates c
            join geography_boundary_source_features f on f.id = c.source_feature_id
            join geography_boundary_import_batches b on b.id = c.import_batch_id
            where b.state_or_ut = 'Karnataka'
              and b.source_system = 'NWDP_GSI_VILLAGE_BOUNDARY'
              and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
              and c.is_active = false
              and c.promotion_status = 'NOT_PROMOTED'
              and c.proposed_scope in ('village', 'village_review')
              and f.metadata ? 'pilot_geometry_materialized_at'
        """)).mappings().one())


def run_materializer(*args: str) -> tuple[int, dict]:
    if OUTPUT.exists():
        OUTPUT.unlink()
    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--limit", "10", "--output", str(OUTPUT), *args],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert_pass("Materializer wrote output", OUTPUT.exists(), proc.stdout)
    return proc.returncode, json.loads(OUTPUT.read_text(encoding="utf-8"))


def main() -> None:
    before_runtime = runtime_counts()

    code, dry = run_materializer()
    assert_pass("Materializer dry-run exits zero", code == 0, dry)
    assert_pass("Materializer dry-run attempts no DB writes", dry.get("db_writes_attempted") is False, dry)
    assert_pass("Materializer dry-run writes no runtime tables", dry.get("runtime_tables_written") is False, dry)
    assert_pass("Materializer dry-run plans 10 staging updates", dry["summary"]["planned_staging_geometry_update_count"] == 10, dry["summary"])
    assert_pass("Materializer dry-run validates 10 geometries", dry["summary"]["validated_geometry_count"] == 10, dry["summary"])

    code, applied = run_materializer("--apply")
    assert_pass("Materializer apply exits zero", code == 0, applied)
    assert_pass("Materializer apply attempts DB writes", applied.get("db_writes_attempted") is True, applied)
    assert_pass("Materializer apply updates 10 staging rows", applied.get("staging_rows_updated") == 10, applied)
    assert_pass("Materializer apply writes no runtime tables", applied.get("runtime_tables_written") is False, applied)
    assert_pass("Materializer apply has zero effective runtime rows", applied.get("runtime_rows_effective") == 0, applied)
    assert_pass("Materializer keeps runtime matching disabled", applied.get("runtime_spatial_matching_changed") is False, applied)
    assert_pass("Materializer keeps Android unchanged", applied.get("android_behavior_changed") is False, applied)

    after_runtime = runtime_counts()
    assert_pass("Runtime counts remain unchanged", after_runtime == before_runtime == {
        "geography_boundary_runtime_sets": 0,
        "geography_boundary_runtime_features": 0,
        "geography_boundary_runtime_crosswalks": 0,
        "geography_boundary_runtime_promotion_events": 0,
    }, after_runtime)

    staged = staged_counts()
    assert_pass("Ten pilot rows have materialized geometry", staged == {
        "pilot_count": 10,
        "hash_count": 10,
        "bbox_count": 10,
        "centroid_count": 10,
        "validated_count": 10,
    }, staged)

    print("=" * 72)
    print("NWDP BOUNDARY PILOT GEOMETRY MATERIALIZER REGRESSION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
